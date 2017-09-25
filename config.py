import re
from inspirehep.modules.search.api import LiteratureSearch
from inspirehep.utils.record import get_value
from utils import xcheck_author, xcheck_author_var, xcheck_title_var, penalty_pages


def get_true_records(recid):
    """ Search for recid and return records """

    search = LiteratureSearch().query('match', control_number=recid)
    for result in search.scan():
        yield result.to_dict()


def get_exact_queries(inspire_record):
    """ Queries using IDs for exact match """
    dois = get_value(inspire_record, 'dois.value')
    arxiv_eprints = get_value(inspire_record, 'arxiv_eprints.value')
    report_numbers = get_value(inspire_record, 'report_numbers.value')

    return [
        {'type': 'exact', 'match': 'dois.value.raw', 'values': dois},
        {'type': 'exact', 'match': 'arxiv_eprints.value.raw', 'values': arxiv_eprints},
        {'type': 'exact', 'match': 'report_numbers.value.raw', 'values': report_numbers}
    ]


def get_fuzzy_queries(inspire_record):
    """ Start fuzzy matching """
    mini_record = get_mlt_record(inspire_record)
    return [{'type': 'fuzzy', 'match': mini_record}]


def get_mlt_record(inspire_record):
    """Returns a reduced record to be used with ElasticSearch
    More Like This query."""
    records = []

    if inspire_record.get('titles'):
        records.append(
            {
                'titles': inspire_record['titles'],
                'boost': 20
            }
        )
    if inspire_record.get('abstracts'):
        records.append(
            {
                'abstracts': inspire_record['abstracts'],
                'boost': 20
            }
        )
    if inspire_record.get('report_numbers'):
        records.append(
            {
                'report_numbers': inspire_record['report_numbers'],
                'boost': 10
            }
        )
    if inspire_record.get('authors'):
        records.append(
            {
                'authors': inspire_record['authors'][:3]
            }
        )
    return records


def validator(record, result):
    """Validate results to avoid false positives."""

    xchecks = {
        xcheck_author_var: 1.0,
        xcheck_title_var: 1.0,
        penalty_pages: 1.0
        }
    score = 0
    weight_sum = 0
    message = ""
    for xcheck, weight in xchecks.items():
        this_score = xcheck(record, result)
        message += '  %s: %s |' % (xcheck, this_score)
        if this_score != None:
            score += this_score * weight
            weight_sum += weight
    if weight_sum > 0:
        score = score / weight_sum
    message = re.sub('<function ', '' ,message)
    message = re.sub(r' at [^>]*>', '' ,message)
    message += 'Total: %s ' % score
#    print message
    return score > 0.5
