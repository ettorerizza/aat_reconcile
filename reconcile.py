# -*- coding: utf-8 -*-

"""
An OpenRefine reconciliation service for the AAT API.

This code is adapted from https://github.com/lawlesst/fast-reconcile
"""
from flask import Flask, request, jsonify
from fuzzywuzzy import fuzz
import getopt
import json
from operator import itemgetter
import re
import requests
from sys import version_info
import urllib
import xml.etree.ElementTree as ET
# Help text processing
import text
# cache calls to the API.
requests_cache.install_cache('getty_cache')

app = Flask(__name__)

# See if Python 3 for unicode/str use decisions
PY3 = version_info > (3,)


# Create base URLs/URIs
api_base_url = 'http://vocabsservices.getty.edu/AATService.asmx/AATGetTermMatch?term='

aat_base_url = 'http://vocab.getty.edu/page/aat/{0}'

# Map the AAT query indexes to service types
default_query = {
    "id": "AATGetTermMatch",
    "name": "AAT term",
    "index": "term"
}

#to add some other services in the future (TGN, ULAN...)
full_query = []

full_query.append(default_query)

# Make a copy of the AAT mappings.
query_types = [{'id': item['id'], 'name': item['name']} for item in full_query]

# Basic service metadata. There are a number of other documented options
# but this is all we need for a simple service.
metadata = {
    "name": "Getty Reconciliation Service",
    "defaultTypes": query_types,
    "view": {
        "url": "{{id}}"
    }
}


def make_uri(getty_id):
    """
    Prepare an AAT url from the ID returned by the API.
    """
    getty_uri = aat_base_url.format(getty_id)
    return getty_uri


def jsonpify(obj):
    """
    Helper to support JSONP
    """
    try:
        callback = request.args['callback']
        response = app.make_response("%s(%s)" % (callback, json.dumps(obj)))
        response.mimetype = "text/javascript"
        return response
    except KeyError:
        return jsonify(obj)


def search(raw_query):
    out = []
    query = text.normalize(raw_query, PY3).strip()
    query_type_meta = [i for i in full_query]
    #query_index = query_type_meta[0]['index']

    # Get the results 
    try:
        if PY3:
            url = api_base_url + urllib.parse.quote(query) + '&logop=and&notes='
        else:
            url = api_base_url + urllib.quote(query) + '&logop=and&notes='
        app.logger.debug("AAT url is " + url)
        resp = requests.get(url)
        results = ET.fromstring(resp.content)
    except getopt.GetoptError as e:
        app.logger.warning(e)
        return out
    for child in results.iter('Preferred_Parent'):
        match = False
        name = re.sub(r'\[.+?\]', '', child.text.split(',')[0]).strip() 
        # the termid is NOT the ID ! We have to find it in the first prefrered parent
        uri = make_uri(re.search(r"\[(.+?)\]", child.text.split(',')[0]).group(1))
        score = fuzz.token_sort_ratio(query, name)
        if score > 95:
            match = True
        app.logger.debug("Label is " + name + " Score is " + str(score) + " URI is " + uri)
        resource = {
            "id": uri,
            "name": name,
            "score": score,
            "match": match,
            "type": query_type_meta
        }
        out.append(resource)
    # Sort this list containing prefterms by score
    sorted_out = sorted(out, key=itemgetter('score'), reverse=True)
    # Refine only will handle top 10 matches.
    return sorted_out[:10]



@app.route("/", methods=['POST', 'GET'])
def reconcile():
    # If a 'queries' parameter is supplied then it is a dictionary
    # of (key, query) pairs representing a batch of queries. We
    # should return a dictionary of (key, results) pairs.
    queries = request.form.get('queries')
    if queries:
        queries = json.loads(queries)
        results = {}
        for (key, query) in queries.items():
            data = search(query['query'])
            results[key] = {"result": data}
        return jsonpify(results)
    # If neither a 'query' nor 'queries' parameter is supplied then
    # we should return the service metadata.
    return jsonpify(metadata)


if __name__ == '__main__':
    from optparse import OptionParser

    oparser = OptionParser()
    oparser.add_option('-d', '--debug', action='store_true', default=False)
    opts, args = oparser.parse_args()
    app.debug = opts.debug
    app.run(host='0.0.0.0')
