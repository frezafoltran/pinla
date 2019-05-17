import random
import boto3
import time
from boto3.dynamodb.conditions import Key
from botocore import exceptions
import re
import operator
from decimal import Decimal
import ast
from threading import Thread
from app.models import Songs
from app import db
from flask import redirect, url_for

dynamodb = boto3.resource("dynamodb")
lyric_table = dynamodb.Table("Lyric")
rhyme_table = dynamodb.Table("Rhyme")


def list_of_rhymes(word):
    """Returns list of words that rhyme with word=word.
    Returns -1 if word is not in database"""
    try:
        response = rhyme_table.get_item(
            Key={
                'id': word
            }
        )
        return response['Item']['rhymes']
    except KeyError:
        return -1


def list_of_sent_id(word):
    """Returns a list of ids for sentences that end with word=word.
    Returns an empty list if no sentences end with word=word.
    Returns -1 if word is not in database"""

    try:
        response = rhyme_table.get_item(
            Key={
                'id': word
            }
        )
        return response['Item']['sent_ids']
    except KeyError:
        return ''

def list_of_similar_words(word):
    """Returns list of words similar to input word"""
    try:
        response = rhyme_table.get_item(
            Key={
                'id': word
            }
        )
        return response['Item']['syns']
    except KeyError:
        return -1



def get_sent_by_id(id):
    """Returns sentence correponding to id=id. Returns -1 if id is not in table"""

    response = lyric_table.get_item(
        Key={
            'id': id
        }
    )

    temp = response['Item']['sent']
    sent = ''
    for word in temp:
        sent += word + ' '

    return sent

def get_rhyme_sent(word):
    """Generates a sentence that rhymes with a given sentence ending with word=word"""
    rhymes = list_of_rhymes(word)
    rhymes_keys = list(rhymes.keys())

    if len(rhymes_keys) != 0:

        # Picks a random word that rhymes with word=word.
        id = []
        while id == []:
            rand = random.randint(0, len(rhymes_keys) - 1)
            rhyme = rhymes_keys[rand]
            id = rhymes[rhyme]

        # Picks a random sentence that ends with rhyme
        rand = random.randint(int(id[0]), int(id[1]))
        sent = [get_sent_by_id(rand), rand]

    # if no rhymes are found, generate sentence that ends with same word
    else:
        rhyme_word = word
        sent_ids = list_of_sent_id(rhyme_word)

        if sent_ids != []:
            rand = random.randint(sent_ids[0], sent_ids[1])
            sent = [get_sent_by_id(rand), rand]

        else:
            return random_sent()

    return sent


def random_sent():

    num_items = lyric_table.item_count
    rand = random.randint(0, num_items - 1)
    return [get_sent_by_id(rand), rand]

def generate_sentence_lastword(last_word):
    """Does the same as generate_sentence, but its given last word instead"""
    return get_rhyme_sent(last_word)

def generate_sentence(sent = ''):
    """Generates sentence that rhymes with sent"""

    if sent == '':
        return random_sent()

    else:

        last_word = sent.split(' ')[-2]
        last_word = last_word.replace('.', '')
        last_word = last_word.replace(',', '')
        last_word = last_word.replace('!', '')

        return get_rhyme_sent(last_word)


def find_suggestions(prec='', suc='', curr=''):
    """Finds suitable replacements for current=curr sentence based on
    preceding=prec and succeding=suc sentences in song"""
    sug_1 = generate_sentence(prec)
    sug_2 = generate_sentence(suc)
    suggestions = [[sug_1[0], sug_1[1]], [sug_2[0], sug_2[1]]]
    return suggestions


def update_table(table, id: str, key: str, value: str):
    """Updates user table, just for saving space.
    Args: table is the table we are updating, id is the id of the item we are updating, key is the attribute name, and
    value is the attribute value.
    """
    table.update_item(
        Key={
            'id': id,
        },
        UpdateExpression='SET ' + key + ' = :val1',
        ExpressionAttributeValues={
            ':val1': value
        }
    )
    return

def change_sent(new, old_id):
    """This function is used in developer mode. It changes the old sentence to new in the Lyric database"""
    #TODO add support to allow old and new to have different last word. Is it necessary?

    temp = new.strip()
    temp = temp.split(' ')

    size = 0
    new_formatted = []
    for word in temp:
        size += 1
        new_formatted.append(word)

    update_table(lyric_table, old_id, 'sent', new_formatted)
    update_table(lyric_table, old_id, 'len', size)

def sent_has_word(id, word):
    """checks if sentence with id=id has word=word"""

    try:
        response = lyric_table.get_item(
            Key={
                'id': id
            }
        )

        return response['Item'][word]
    except KeyError:
        return 0


def get_good_sent_batch_helper(temp, rhyme, rand_i, syns):

    if not temp:
        return []

    good_sent = []
    response = dynamodb.meta.client.batch_get_item(
        RequestItems={
            'Lyric': {
                'Keys': [
                    {'id': id} for id in temp
                ],
                'ConsistentRead': True
            }
        },
        ReturnConsumedCapacity='TOTAL'
    )

    for item in response['Responses']['Lyric']:

        for h in syns:
            try:
                item[h]
                sent = ''
                for word in item['sent']:
                    sent += word + ' '
                good_sent.append([sent, item['id'], rhyme[rand_i]])
                break
            except KeyError:
                continue

    return good_sent


def get_good_sent_rand(syns, ids, t_lim, rhyme, rand_i):

    good_sent = []
    t2 = time.time()

    for j in ids[rand_i]:

        start = j[0]

        if start + 100 > j[1]:
            temp = [k for k in range(int(start), int(j[1]))]
            good_sent += get_good_sent_batch_helper(temp, rhyme, rand_i, syns)
            break

        while start+100 < j[1]:

            temp = [k for k in range(int(start), int(start)+100)]
            start += 100

            good_sent += get_good_sent_batch_helper(temp, rhyme, rand_i, syns)

            if time.time() - t2 > t_lim:
                return good_sent

    return good_sent


def sentence_with(words, rhyme=[], t_lim=7):
    """Generates a sentence that contains one of the input words.
    mod takes a list of rhymes instead. Assume all entries in rhyme = [] are single words

    Time complexity: due to call to get_good_sent_rand(words, ids, t_lim, rhyme, rand_i).
    limit time is 3*t_lim. """

    items = []

    if rhyme == []:

        if not words:
            words = ['bitch']

        filt = Key(words[0]).eq(1)
        for word in words:
            filt |= Key(word).eq(1)

        while items == []:

            r1 = random.randint(1, lyric_table.item_count - 1)

            response = lyric_table.scan(
                FilterExpression=filt,
                ExclusiveStartKey={'id': r1},
                )
            items = response['Items']

        sentences = []
        for item in items:
            sent = ''

            try:
                for word in item['sent']:
                    sent += word + ' '
                sentences.append([sent, item['id']])

            except TypeError:
                continue
        if len(sentences) > 10:
            return sentences[:10]
        else:
            return sentences
    else:

        # each entry of ids corresponds to the ranges for a given word in rhyme list input
        # ids = [[[r1, r2], [r3, r4]...], [[r5, r6],...], ...]
        ids = []
        for item in rhyme:
            temp = list_of_rhymes(item)
            ids.append(list(filter(None, list(temp.values()))))

        rand = random.sample(range(len(ids)), len(ids))
        good_sent = []

        t1 = time.time()
        for rand_i in rand:
            if time.time()-t1 > t_lim*3 or len(good_sent)>8:
                return good_sent
            good_sent += get_good_sent_rand(words, ids, t_lim, rhyme, rand_i)

        return good_sent


# --------------------------------------------- Scrapping methods
proxy_table = dynamodb.Table("Proxy")
from bs4 import BeautifulSoup
import requests
import inflect

def get_proxy():
    """
    Looks up a random proxy from DynamoDB table and returns it
    :returns array of two strings, IP and port:
    """
    response = proxy_table.get_item(
        Key={
            'id': "num_proxies"
        }
    )
    item = response['Item']
    num_proxies = int(item['value'])
    choice = random.randint(0, num_proxies-1)
    response = proxy_table.get_item(
        Key={
            'id': str(choice)
        }
    )
    item = response['Item']
    proxy_response = [item["ip"], item["port"]]
    return proxy_response

def word_in_rhyme(word):
    """Check if word is in rhyme table"""
    try:
        response = rhyme_table.get_item(
            Key={
                'id': word
            }
        )
        response['Item']
        return 1
    except KeyError:
        return -1


def synonym_scrape(word: str, lim=10):
    """
    This function gets the synonyms of a given word from thesaurus.com
    """

    link = "https://www.thesaurus.com/browse/" + word
    # phonetic = [""]
    script = requests.get(link)
    soup = BeautifulSoup(script.content, 'html.parser')
    engine = inflect.engine()

    if soup == "" or soup == None:
        print("Using proxy")
        proxy = get_proxy()
        script = requests.get(link, proxies={"http": proxy})
        soup = BeautifulSoup(script.content, 'html.parser')
        print(soup.prettify())

    try:
        temp = str(list(soup.findAll('ul', {'class': "css-1lc0dpe et6tpn80"})))
        all_syns = re.findall('>[a-z]+</a></span>', temp)

        syns = []
        for word in all_syns:
            syn = word[1:-11]
            if syn != '':
                if word_in_rhyme(syn) == 1:
                    syns.append(syn)
                plural = engine.plural(syn)
                if word_in_rhyme(plural) == 1:
                    syns.append(plural)
            if len(syns) > lim:
                break

        return syns



    except IndexError:
        print("{} was not found".format(word))
        return -1


def initialize_syns(word, w2vec_syns = ''):
    """Creates list of dictionary to be used when updating the syns entry in the rhyme_table"""

    if w2vec_syns == '':
        sim = list_of_similar_words(word)
    else:
        sim = w2vec_syns

    # in case database was already updated
    if len(sim) == 2:
        print('ici')
        return sim

    syns = synonym_scrape(word)


    inter = set(syns) & set(sim)
    print(inter)

    temp_1 = {}
    for item in sim:
        if item in inter:
            temp_1[item]=1
        else:
            temp_1[item]=0

    temp_2 = {}
    for item in syns:
        if item not in inter:
            temp_2[item]=0

    return [temp_1, temp_2]

def list_of_similar_words_updated(word):

    syns = list_of_similar_words(word)
    try:
        temp = syns[0].keys()

    except AttributeError:
        syns = initialize_syns(word, w2vec_syns=syns)
        update_table(rhyme_table, word, 'syns', syns)

    syns[0][word] = 0

    for key in syns[0]:
        syns[0][key] = int(syns[0][key])
    for key in syns[1]:
        syns[1][key] = int(syns[1][key])

    return syns


def string_to_dic(syns_formatted):
    """Input is a string representation of syns (from local databse). outputs list of two dictionaries syns
    to be used by sentence_related.
    input is assumed to be str;dic1;dic2"""

    t = syns_formatted.split(';')
    t1 = ast.literal_eval(t[1])
    t2 = ast.literal_eval(t[2])

    return [t1, t2]


def sentence_related(syns, rhyme=[], num_words=5, t_lim = 7):
    """Generates a sentence that contains a word in syns list and rhymes with rhyme
    mod version does the same oa other, but take a list of rhymes instead of a rhyme
    Time complexity: due to sentence_with(words, rhyme) call (takes maximum of per call)"""

    # choose top num_words words to build sentence
    words = []
    for i in range(0,num_words):

        try:
            max_w2vec = max(syns[0].items(), key=operator.itemgetter(1))[0]
            max_dic_syn = max(syns[1].items(), key=operator.itemgetter(1))[0]
        except ValueError:
            syns = [syns[0],syns[0]]
            max_w2vec = max(syns[0].items(), key=operator.itemgetter(1))[0]
            max_dic_syn = max(syns[1].items(), key=operator.itemgetter(1))[0]

        if syns[0][max_w2vec] > syns[1][max_dic_syn]:
            words.append(max_w2vec)
            syns[0][max_w2vec] = -1

        elif syns[0][max_w2vec] < syns[1][max_dic_syn]:
            words.append(max_dic_syn)
            syns[1][max_dic_syn] = -1

        elif syns[0][max_w2vec] <= 0:
            r = random.randint(0,1)
            if r == 0:
                words.append(max_w2vec)
                syns[0][max_w2vec] = -1
            else:
                words.append(max_dic_syn)
                syns[1][max_dic_syn] = -1

        #all values are negative => all have been picked. fill rest of vector with best word (words[0])
        else:
            break


    if rhyme == []:
        return sentence_with(words)

    else:
        return sentence_with(words, rhyme, t_lim=t_lim)


def update_syns_rank(word, lyric):
    """This function updates the syns scores for word=word based on the lyric input.
    For now, it simply increases the count of each word that is in both syns and in lyric by
    1 and commits change to database. lyric is assumed to have format:
    lyric = ;s1;s2;s3...
    The function also assumes that word already has syns in the new format [{},{}]. This makes sense since
    this function is only called after song is completed"""

    lyric = lyric.strip(' ')
    lyric = lyric.split(';')
    syns = list_of_similar_words(word)
    keys_1 = syns[0].keys()
    keys_2 = syns[1].keys()

    for sentence in lyric:
        words = sentence.strip(' ').split(' ')
        for w in words:
            if w in keys_1:
                syns[0][w] += 1
            elif w in keys_2:
                syns[1][w] += 1

    print(syns)
    update_table(rhyme_table, word, 'syns', syns)
    return

def update_rhyme_ids(word):
    """Updates the rhymes column in rhyme table to include the sent ids of each rhyme of a given word"""
    rhymes = list_of_rhymes(word)

    new_rhyme_list = {}
    for r in rhymes:
        ids = list_of_sent_id(r)
        if ids == '':
            ids = []
        new_rhyme_list[r] = ids

    update_table(rhyme_table, word, 'rhymes', new_rhyme_list)


def populate_custom_song_async(syns, song_id, thread=True, first=False):
    """"populates related_thr and rhyme_related_thr columns of Song table.
    syns the list of synonims of a given word (along with their scores)"""

    song = Songs.query.filter_by(id=song_id).first()
    related = sentence_related(syns)
    # gets last words from sentences in new_related
    last_words = []
    for item in related:
        temp = item[0].strip(' ').split(' ')[-1]
        last_words.append(temp)

    # sent has as keys last words from new_related. The values are sentences that are related to self.song_about()
    # and rhyme with the key
    sent = {}
    for word in last_words:
        sent[word] = []

    for i in range(1):
        print('thread happening')
        temp = sentence_related(list_of_similar_words_updated(song.song_about()), rhyme=last_words, num_words=10)
        for s in temp:
            sent[s[2]].append([s[0], s[1]])

    first_to_add = song.update_related(related, last_words, sent, thread=thread)
    db.session.commit()

    if first:
        song.update_related_id(id=0, action='used', line_being_used=1)
        lyric = [related[first_to_add][0], int(related[first_to_add][1])]
        song.update_lyric(lyric)
        song.about = song.about[1:]
        print('----------------------------------------------- MAIN THREAD ENDED')
        print('song_about: ', song.about)

    db.session.commit()



def populate_custom_song(syns, song_id, thread=True, first=False):

    Thread(target=populate_custom_song_async, args=(syns, song_id, thread, first, )).start()


def get_rhyme_related_id_by_line_id(rhyme_related_ids, line_id):
    #line_id is assumed to start at 1. related_id is the positional id of sentence

    # TODO Need to check if this is going to cause problems if we try to access while thread is happening
    #  TODO if it does, the idea is to return -1 and generate a new rhyming sentence.
    index_1 = rhyme_related_ids.find(str(line_id)+'-')


    # found in the non-thread
    if index_1 != -1:
        all_index = [m.start() for m in re.finditer(';', rhyme_related_ids)]

        for i in range(len(all_index)):
            if all_index[i] > index_1:

                #find subindex (related to & flag)
                all_index_2 = [m.start() for m in re.finditer('&', rhyme_related_ids[all_index[i-1]:all_index[i]])]
                for j in range(len(all_index_2)):

                    if rhyme_related_ids[all_index_2[j]+all_index[i-1]+1:all_index_2[j]+all_index[i-1]+1+len
                            (str(line_id))] == str(line_id):
                        return [i - 1, j, False]

        i = len(all_index)
        all_index_2 = [m.start() for m in re.finditer('&', rhyme_related_ids[all_index[i - 1]:])]
        for j in range(len(all_index_2)):

            if rhyme_related_ids[
               all_index_2[j] + all_index[i - 1] + 1:all_index_2[j] + all_index[i - 1] + 1 + len(str(line_id))] == str(
                    line_id):
                return [len(all_index) - 1, j, False]

    return [-1, -1, -1]



#rhyme_related = ';&business making sure that my calls &feed me dope and some false ;&all business if you hear cops ;&no business sitting on blades &peeps talking bout your box braids &no business sitting on blades &feed them on no dates &tried to feed them on dates &feed of my dates &to feed them on dates ;&a business man with racks &business up now he need ajax &it feed the motherfucker named blacks &you feed the motherfucker named blacks &even feed the motherfucker named blacks &business with the xanax'
rhyme_related_ids=  ';&0-1116318&0-3450951;&0-834343;&0-3037430&0-1693448&0-3037430&0-1636647&0-1636710&1-1636842&0-1636964;&0-735320&0-3374819&0-5130126&0-5130177&2-5130166&12-2954832'

[id, id2, flag] = get_rhyme_related_id_by_line_id(rhyme_related_ids, 12)
print(id, id2)






















