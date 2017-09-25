
import re
import json
import math

DRUCK = False

def xcheck_author(record, result):
    """
    Are authors consistent?
    Compare first 5 authors of both records
    """
    from inspire_json_merger.comparators import AuthorComparator
    score = 0.5
    if not record.get('authors'):
        return score
    if not result.record.get('authors'):
        return score
    try:
        authors_record = min(len(record['authors']), 5)
        authors_match_record = min(len(result.record['authors']), 5)
        matches = len(
            AuthorComparator(
                record['authors'][:authors_record],
                result.record['authors'][:authors_match_record]
            ).matches
        )
        score = matches / float(max(authors_record, authors_match_record))
    except:
        # FIXME json_merger fails internally in some author comparison
        pass
    return score

def xcheck_author_var(record, result):
    """
    Are authors consistent?
    Is the number of authors consistent? Slightly different -> degrade score
    Are the first 2 authors in the matched record?
    No authors in either record -> ignore
    """
    from inspire_json_merger.comparators import AuthorComparator
    score = None
    if not record.get('authors'):
        return score
    if not result.record.get('authors'):
        return score
    xauthors = []
    for a in result.record.get('authors'):
        if 'full_name' in a:
            xauthors.append(a['full_name'])

    num_authors_record = len(record['authors'])
    num_authors_match = len(result.record['authors'])
    num_score = 1.0
    if (num_authors_record > 1 and num_authors_match > 1):
        if (abs(num_authors_record - num_authors_match) > 3 and
            abs(math.log(num_authors_record / float(num_authors_match))) > 0.3):
            if DRUCK:
                print num_authors_match, 'different'
            return 0
        if (abs(num_authors_record - num_authors_match) > 2 and
            abs(math.log(num_authors_record / float(num_authors_match))) > 0.2):
            num_score = 0.7

    if DRUCK:
        for a in result.record['authors'][:2]:
            print json.dumps(a, sort_keys=True, indent=4)

    try:
        num_authors_record_2 = min(num_authors_record, 2)
        matches = len(
            AuthorComparator(
                record['authors'][:num_authors_record_2],
                result.record['authors']
            ).matches
        )
        score = matches / float(max(num_authors_record_2, num_authors_match))
        score = score * num_score
        if DRUCK:
            print score, xauthors[:2]
    except:
        # FIXME json_merger fails internally in some author comparison
        print 'ERROR', xauthors[:2]
        pass

    return score


def title_words(title):
    """Trying to find useful words in title"""

    frequent_words = set(['a', 'at', 'to', 'on', 'of', 'in',
                   'and', 'for', 'not', 'the', 'with', 'from'])
    tokens = []
    for word in re.sub('[^a-z0-9]', ' ', title['title'].lower()).split():
        if len(word) > 1:
            tokens.append(word)
    return set(tokens) - frequent_words


def xcheck_title_var(record, result):
    """
    Is title consistent?
    Count words common in both titles, trying to get rid of math.
    No title in either record -> ignore
    """
    from itertools import product
    if not record.get('titles'):
        return None
    if not result.record.get('titles'):
        return None

    record_titles = []
    for title in record['titles']:
        if title_words(title):
            record_titles.append(title_words(title))
    if not record_titles:
        return None

    result_titles = []
    for title in result.record['titles']:
        if title_words(title):
            result_titles.append(title_words(title))
    if not result_titles:
        return None

    max_score = 0
    for titles in product(record_titles, result_titles):
        record_tokens = titles[0]
        result_tokens = titles[1]
        try:
            score = len(record_tokens & result_tokens) / \
                float(len(record_tokens | result_tokens))
        except:
            score = 0
        if score > max_score:
            max_score = score
        if DRUCK:
            print score, titles[1]
    return max_score

def xcheck_title(record, result):
    """
    Is title consistent?
    Count words common in both titles.
    No title in either record -> ignore
    """
    from itertools import product
    if record.get('titles') and result.record.get('titles'):
        title_max_score = 0.0
        record_titles = [r['title'].lower() for r in record['titles']]
        result_titles = [r['title'].lower() for r in result.record['titles']]

        for titles in product(record_titles, result_titles):
            record_tokens = set(titles[0].split())
            result_tokens = set(titles[1].split())
            title_score = len(record_tokens & result_tokens) / \
                float(len(record_tokens | result_tokens))
            if title_score > title_max_score:
                title_max_score = title_score
    else:
        title_max_score = None

    return title_max_score

def penalty_date(record, result):
    """
    Conflicting year? User earliest date.
    Same year doesnt indicate same paper,
    but different year indicates different paper.
    I.e. return penalty but never agreement.
    """
    
    #FIXME get year the same way as for texkey generation
    record_year = 1999 # int(record.get(....))
    result_year = 2000 # int(result.get(....))
    
    diff_year = abs(record_year - result_year)
    if diff_year > 8:
        score = 0.2
    else:
        score = None
    return score
 
def penalty_pages(record, result):
    """
    Conflicting number of pages? 
    Same number of pages dont indicate same paper,
    but different pages indicate different paper.
    I.e. return penalty but never agreement.
    """
    
    record_pages = record.get('number_of_pages')
    result_pages = result.record.get('number_of_pages')
    
    if record_pages and result_pages and record_pages > 1 and result_pages > 1:
        relation = abs(math.log(result_pages / float(record_pages)))
        if DRUCK:
            print 'Pages:', record_pages, result_pages, relation
        if relation > 0.6: # e.g. 20/37
            return 0.1
        elif relation > 0.3 and abs(result_pages - record_pages) > 4 : # e.g. 50/68
            return 0.3
    return None
    
