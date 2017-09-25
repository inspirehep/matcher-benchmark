import argparse
import datetime
import glob
import os
import json

from dojson.contrib.marc21.utils import create_record as marc_create_record

from invenio_matcher.api import match as _match

from inspire_dojson.processors import overdo_marc_dict
from inspirehep.modules.migrator.tasks.records import split_stream
from inspirehep.utils.record import get_value
from inspirehep.utils.record_getter import get_db_record
from inspirehep.factory import create_app

from config import get_true_records, get_exact_queries, get_fuzzy_queries, validator

DRUCK = False

def generate_doi_map():
    with open('test_matches_clean.txt', 'r') as fd:
        result = {}
        for line in fd:
            doi, recid = line.split('--')
            recid = recid.strip()
            result[doi.strip()] = recid
        return result


def generate_recid_map():
    with open('manual_matches.txt', 'r') as fd:
        result = {}
        for line in fd:
            recid1, recid2 = line.split('--')
            recid2 = recid2.strip()
            result[recid1.strip()] = recid2
        return result

def generate_no_match_list():
    with open('no_match.txt', 'r') as fd:
        return fd.read().splitlines()


def is_good_match(doi_match_map, recid_match_map, dois, control_number, matched_recid):
    def _got_match(dictionary, key, value):
        return dictionary.get(key) == value

    if dois:
        if any([_got_match(doi_match_map, doi, str(matched_recid)) for doi in dois]):
            return True

    if control_number:
        if _got_match(recid_match_map, str(control_number), str(matched_recid)):
            return True

    return False


def write(content, filename):
    with open(filename, 'w') as fd:
        fd.write(content)


def main(args):
    total = 0
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0
    very_fuzzy = {'E':0, 'M':0}
    multiple_exact = 0  # Keep track of cases where multiple records match a exact query
    doi_match_map = generate_doi_map()
    recid_match_map = generate_recid_map()
    no_match_list = generate_no_match_list()

    filenames = []

    for filename in args.names:
        if os.path.isfile(filename):
            filenames.append(filename)
        else:
            filenames.extend(glob.glob(filename + '/*.xml'))

    if args.output:
        false_positives_dir = 'false_positives_{0}'.format(datetime.datetime.now().isoformat())
        false_negatives_dir = 'false_negatives_{0}'.format(datetime.datetime.now().isoformat())
        os.makedirs(false_positives_dir)
        os.makedirs(false_negatives_dir)

    app = create_app()
    with app.app_context():
        app.config['DEBUG'] = False
        for filename in filenames:
            with open(filename, 'r') as fd:
                for marcxml in split_stream(fd):
                    marc_record = marc_create_record(marcxml, keep_singletons=False)
                    try:
                        inspire_record = overdo_marc_dict(marc_record)
                    except TypeError:
                        # Some bad metadata in the record - skip
                        pass

                    control_number = get_value(inspire_record, 'control_number')
                    dois = get_value(inspire_record, 'dois.value')
                    arxiv_eprints = get_value(inspire_record, 'arxiv_eprints.value')

                    if not dois and not control_number:
                        # FIXME all the correct/incorrect match files are based on doi
                        continue

                    total += 1

                    print 'Going to match DOIs: ', dois
                    print 'Going to match arXiv eprints: ', arxiv_eprints

                    if DRUCK:
                        authors = []
                        if inspire_record.get('authors'):
                            for a in inspire_record.get('authors'):
                                if 'full_name' in a:
                                    authors.append(a['full_name'])

                        print 'Looking for:'
                        print inspire_record.get('titles')
                        print len(authors), authors[:2]
                        print inspire_record.get('number_of_pages'), 'Pages'

                    # Step 1 - apply exact matches
                    queries_ = get_exact_queries(inspire_record)
                    matched_exact_records = list(_match(
                        inspire_record,
                        queries=queries_,
                        index='records-hep',
                        doc_type='hep'
                    ))

                    if len(matched_exact_records) == 1:
                        very_fuzzy['E'] += 1
                        matched_recid = matched_exact_records[0].record.get('control_number')
                        if is_good_match(doi_match_map, recid_match_map, dois, control_number, matched_recid):
                            true_positives += 1
                            print '++ Got a good match! with recid: ', matched_recid
                        else:
                            false_positives += 1
                            if args.output:
                                write(marcxml, false_positives_dir + os.path.sep + str(total) + '.xml')
                                write(json.dumps(matched_exact_records[0].record), false_positives_dir + os.path.sep + str(total) + '_in.json')
                            print '-- Got a wrong match', matched_exact_records[0].record.get('control_number')
                        continue
                    elif len(matched_exact_records) > 1:
                        # FIXME Treat multiple exact matches as fuzzy match?
                        false_positives += 1
                        multiple_exact += 1
                        very_fuzzy['M'] += 1
                        if args.output:
                            write(marcxml, false_positives_dir + os.path.sep + str(total) + '.xml')
                            write(json.dumps(matched_exact_records[0].record), false_positives_dir + os.path.sep + str(total) + '_in.json')

                        print '-- More than one match found: ', [m.record.get('control_number') for m in matched_exact_records]
                        continue

                    print 'Did not find a match for DOIs or arXiv ePrints'
                    # Step 2 - apply fuzzy queries
                    print 'Executing mlt query...'

                    queries_ = get_fuzzy_queries(inspire_record)
                    matched_fuzzy_records = list(_match(
                        inspire_record,
                        queries=queries_,
                        index='records-hep',
                        doc_type='hep',
                        validator=validator
                    ))

                    num_matched_fuzzy_records = len(matched_fuzzy_records)
                    if num_matched_fuzzy_records > 10:
                        num_matched_fuzzy_records = 10
                    if num_matched_fuzzy_records in very_fuzzy:
                        very_fuzzy[num_matched_fuzzy_records] += 1
                    else:
                        very_fuzzy[num_matched_fuzzy_records] = 1
                    if num_matched_fuzzy_records >= 5:
                        matched_fuzzy_records = matched_fuzzy_records[2:]

                    match_included = False
                    for first_result in matched_fuzzy_records:
                        matched_recid = first_result.record.get('control_number')
                        print '++ Fuzzy result found: ', matched_recid
                        if is_good_match(doi_match_map, recid_match_map, dois, control_number, matched_recid):
                            match_included = True
                            true_recid = matched_recid
                            break

                    if match_included:
                        true_positives += 1
                        print '++ Got a good match! with recid: ', true_recid
                    elif len(matched_fuzzy_records) >= 1:
                        false_positives += 1
                        if args.output:
                            print '-- False positive - check {0} file'.format(str(total) + '.xml')
                            write(marcxml, false_positives_dir + os.path.sep + str(total) + '.xml')
                            if len(matched_fuzzy_records) >= 1:
                                num = 0
                                for mfr in matched_fuzzy_records[:3]:
                                    write(json.dumps(mfr.record, sort_keys=True, indent=4, separators=(',', ': ')),
                                        false_positives_dir + os.path.sep + str(total) + '.' + str(num) + '.in.json')
                                    num += 1
                    else:
                        # No record matched, check if it was a true negative
                        if dois and (set(no_match_list) & set(dois) != set()):
                            true_negatives += 1
                        else:
                            false_negatives += 1
                            if args.output:
                                print '-- False negative - check {0} file'.format(str(total) + '.xml')
                                write(marcxml, false_negatives_dir + os.path.sep + str(total) + '.xml')
                                true_match = []
                                if dois:
                                    for doi in dois:
                                        if doi in doi_match_map:
                                            true_match.append(int(doi_match_map[doi]))
                                elif str(control_number) in recid_match_map:
                                    true_match.append(int(recid_match_map[str(control_number)]))
                                else:
                                    print control_number, 'not in recid_match_map'

                                if len(set(true_match)) > 0:
                                    for true_record in get_true_records(true_match[0]):
                                        write(json.dumps(true_record, sort_keys=True, indent=4, separators=(',', ': ')),
                                            false_negatives_dir + os.path.sep + str(total) + '.true.json')
                                        break


                        print '\n'

        print '#### STATS ####'
        print 'Total analyzed: ', total
        print 'True positives: ', true_positives
        print 'False positives: ', false_positives
        print 'True negatives: ', true_negatives
        print 'False negatives: ', false_negatives
        print 'Duplicate exact match: ', multiple_exact
        print 'Very fuzzy match: ', very_fuzzy
        print '------------------------'
        if true_positives + false_positives > 0:
            precision = true_positives/float(true_positives + false_positives)
        else:
            precision = 0
        if true_positives + false_negatives > 0:
            recall = true_positives/float(true_positives + false_negatives)
        else:
            recall = 0
        print 'Precision: ', precision
        print 'Recall: ', recall
        if precision or recall:
            print 'F1 Score: ', 2.0/(1/precision + 1/recall)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Test invenio-matcher.')
    parser.add_argument('names', nargs='+', help='File(s) or directory(ies) to run matcher against.')
    parser.add_argument('--output', help='Output files with false positives and false negatives', action='store_true')
    args = parser.parse_args()
    main(args)
