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

"""
def sentence_with_mod(words, rhyme=[]):
    #Generates a sentence that contains one of the input words.
    #mod takes a list of rhymes instead. Assume all entries in rhyme = [] are single words

    t1 = time.time()
    items = []

    if rhyme == []:
        while items == []:

            r1 = random.randint(1, lyric_table.item_count - 1)

            response = lyric_table.scan(
                FilterExpression=Key(words[0]).eq(1)|Key(words[1]).eq(1)|Key(words[2]).eq(1)|Key(words[3]).eq(1)|Key(words[4]).eq(1),
                ExclusiveStartKey={'id': r1},
                )
            items = response['Items']
    else:

        # each entry of ids corresponds to the ranges for a given word in rhyme list input
        # ids = [[[r1, r2], [r3, r4]...], [[r5, r6],...], ...]
        ids = []
        for item in rhyme:
            temp = list_of_rhymes(item)
            #print(temp)
            ids.append(list(filter(None, list(temp.values()))))

        for j in range(len(ids)):
            for i in range(len(ids[j])):
                if ids[j][i][0] > ids[j][i][1]:
                    temp = ids[j][i][0]
                    ids[j][i][0] = ids[j][i][1]
                    ids[j][i][1] = temp


        #TODO Understand the bound in range(min(len(rhyme), 7))
        filt = Key('id').between(0, 0)
        for j in range(3):
            for i in range(len(ids[j])):
                filt |= Key('id').between(int(ids[j][i][0]), int(ids[j][i][1]))

        # for now assume rhyme has length 3 at least.
        items = []
        while items == []:
            print('loop:', time.time() - t1)

            #r1 = random.randint(1, lyric_table.item_count - 1)
            r1 = random.randint(0,len(rhyme)-1)
            try:
                r2 = random.randint(0,len(ids[r1])-1)
                r3 = random.randint(ids[r1][r2][0], ids[r1][r2][1])
            except ValueError:
                r3 = random.randint(1, lyric_table.item_count - 1)

            try:

                response = lyric_table.scan(
                    FilterExpression=(Key(words[0]).eq(1) | Key(words[1]).eq(1) | Key(words[2]).eq(1) | Key(words[3]).eq(1)| Key(words[4]).eq(1)) & filt,

                    ExclusiveStartKey={'id': r3},
                )

                items = response['Items']

            except (exceptions.ClientError):
                print('exception')
                continue

    sentences = []
    for item in items:
        sent = ''

        # get which word sent rhymes with
        if rhyme != []:
            id = item['id']
            found = -1
            for j in range(len(ids)):
                for i in range(len(ids[j])):
                    if id <= ids[j][i][1] and id >= ids[j][i][0]:
                        found = j
                        break
                if found == j:
                    break
        try:
            for word in item['sent']:
                sent += word + ' '
            if rhyme != []:
                sentences.append([sent, item['id'], rhyme[found]])
            else:
                sentences.append([sent, item['id']])

        except TypeError:
            continue

    if len(sentences) > 10:
        return sentences[:10]
    else:
        return sentences
        
        """

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

        print('ids: ', ids)
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


def populate_custom_song_async(syns, song_id, thread=True):
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
        print(temp)
        for s in temp:
            sent[s[2]].append([s[0], s[1]])

    song.update_related(related, last_words, sent, thread=thread)
    db.session.commit()



def populate_custom_song(syns, song_id, thread=True):

    Thread(target=populate_custom_song_async, args=(syns, song_id, thread, )).start()


#words = ['adolescence', 'aluminum', 'applying', 'arab', 'ate', 'yesterday', 'writer', 'triceps']

words = []


for word in words:

    print('------------------------------------------------------------------')
    print(word)
    syns = list_of_similar_words_updated(word)
    print('syns: ', syns)
    related = sentence_related(syns)
    print('related: ', related)

    last_words = []
    for item in related:
        temp = item[0].strip(' ').split(' ')[-1]
        last_words.append(temp)
    print('last_words:', last_words)



    t_out = time.time()
    temp = []
    while temp == [] and time.time()-t_out < 400:
        print('again')
        temp = sentence_related(syns, rhyme=last_words, num_words=10)
        print(time.time()-t_out)

    print('total time: ', time.time()-t_out)
    print(temp)
    print(len(temp))


# -------------------------------------- JUST FOR TESTING

def get_rhyme_related_by_id(rhyme_related, rhyme_related_ids, id, thresh=False):
    """"""

    # find the range in rhyme_related and rhyme_related_ids that correspond to the requested related sentence
    if not thresh:
        all_index = [m.start() for m in re.finditer(';', rhyme_related)]
        if id + 1 == len(all_index):
            possible_rhyme_related = rhyme_related[all_index[id]+1:]
        else:
            possible_rhyme_related = rhyme_related[all_index[id]+1: all_index[id+1]]

        all_index_2_perm = [m.start() for m in re.finditer(';', rhyme_related_ids)]
        if id + 1 == len(all_index_2_perm):
            possible_rhyme_related_ids = rhyme_related_ids[all_index_2_perm[id]+1:]
        else:
            possible_rhyme_related_ids = rhyme_related_ids[all_index_2_perm[id]+1: all_index_2_perm[id+1]]

    all_index = [m.start() for m in re.finditer('&', possible_rhyme_related)]
    all_index_2 = [m.start() for m in re.finditer('&', possible_rhyme_related_ids)]

    c = 0
    id_new = -1
    for i in all_index_2:
        if possible_rhyme_related_ids[i + 1] == '0':
            id_new = c
            break
        c += 1

    if id_new == -1:
        return []

    if id_new + 1 == len(all_index):
        sent = possible_rhyme_related[all_index[id_new]+1:]
    else:
        sent = possible_rhyme_related[all_index[id_new]+1: all_index[id_new+1]]

    if id_new + 1 == len(all_index_2):
        temp = possible_rhyme_related_ids[all_index_2[id_new] + 1:].find('-') + all_index_2[id_new] + 1
        sent_id = possible_rhyme_related_ids[temp+1:]

    else:
        temp = possible_rhyme_related_ids[all_index_2[id_new] + 1:].find('-') + all_index_2[id_new] + 1
        sent_id = possible_rhyme_related_ids[temp + 1: all_index_2[id_new + 1]]

    print(possible_rhyme_related, possible_rhyme_related_ids)

    return [sent, sent_id]

def update_rhyme_related_id(rhyme_related_ids, sentence_id=-1, line_being_used=-1, action='new', thread=False):
    """ Updates the dynamodb id and line_being_used id of sentences in song.related column
            Inputs:
            sentence_id = dynamodb id of sentence
            line_being_used = line in song that sentence is being used (index starts at 1)
            action = what to to with sentence
            """

    if not thread:

        #all_index = [m.start() for m in re.finditer(';', rhyme_related_ids)]

        # adds new sentence. this is only called from update_related
        if action == 'new':
            rhyme_related_ids = rhyme_related_ids + '&0-' + str(sentence_id)


        # updates status of sentence when sentence is added to ongoing lyrics
        elif action == 'used':

            ind = rhyme_related_ids.find('-'+sentence_id)
            rhyme_related_ids = rhyme_related_ids[:ind-1] + str(line_being_used) + rhyme_related_ids[ind:]

        # when user deletes sentence from rhyme_related_ids, we simply set its flag to 0 (as unused)
        elif action == 'del':
            ind = rhyme_related_ids.find('-' + sentence_id)
            rhyme_related_ids = rhyme_related_ids[:ind - 1] + '0' + rhyme_related_ids[ind:]


        print(rhyme_related_ids)


"""
rhyme_related = ';&business making sure that my calls &feed me dope and some false ;&all business if you hear cops ;&no business sitting on blades &peeps talking bout your box braids &no business sitting on blades &feed them on no dates &tried to feed them on dates &feed of my dates &to feed them on dates ;&a business man with racks &business up now he need ajax &it feed the motherfucker named blacks &you feed the motherfucker named blacks &even feed the motherfucker named blacks &business with the xanax'
rhyme_related_ids=  ';&0-1116318&0-3450951;&0-834343;&0-3037430&0-1693448&0-3037430&0-1636647&0-1636710&0-1636842&0-1636964;&0-735320&0-3374819&0-5130126&0-5130177&0-5130166&0-2954832'

[sent, sent_id] = get_rhyme_related_by_id(rhyme_related, rhyme_related_ids, 0, thresh=False)

update_rhyme_related_id(rhyme_related_ids, sentence_id=sent_id, line_being_used=14, action='used', thread=False)
"""
print(len(';&apple and eagle is the soundtrack &pressure i get any sack &the barrel watch the whole sack &a star like a tack &star flier than a tack &apple and eagle is the soundtrack &pressure i get any sack &the barrel watch the whole sack &a star like a tack &star flier than a tack &the star and your wack &rock star girls call me wack &a star and they fucking whack ;&apple and eagle is the soundtrack &pressure i get any sack &the barrel watch the whole sack &a star like a tack &star flier than a tack &apple and eagle is the soundtrack &pressure i get any sack &the barrel watch the whole sack &a star like a tack &star flier than a tack &the star and your wack &rock star girls call me wack &a star and they fucking whack ;&apple and eagle is the soundtrack &pressure i get any sack &the barrel watch the whole sack &a star like a tack &star flier than a tack &apple and eagle is the soundtrack &pressure i get any sack &the barrel watch the whole sack &a star like a tack &star flier than a tack &the star and your wack &rock star girls call me wack &a star and they fucking whack'))



















