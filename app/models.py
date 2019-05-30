from datetime import datetime
from hashlib import md5
from time import time
from flask import current_app, flash
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from app import db, login
from app.search import add_to_index, remove_from_index, query_index
import re
import random


class SearchableMixin(object):
    @classmethod
    def search(cls, expression, page, per_page):
        ids, total = query_index(cls.__tablename__, expression, page, per_page)
        if total == 0:
            return cls.query.filter_by(id=0), 0
        when = []
        for i in range(len(ids)):
            when.append((ids[i], i))
        return cls.query.filter(cls.id.in_(ids)).order_by(
            db.case(when, value=cls.id)), total

    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': list(session.new),
            'update': list(session.dirty),
            'delete': list(session.deleted)
        }

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['update']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['delete']:
            if isinstance(obj, SearchableMixin):
                remove_from_index(obj.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in cls.query:
            add_to_index(cls.__tablename__, obj)

db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)


followers = db.Table(
    'followers',
    db.Column('follower_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('followed_id', db.Integer, db.ForeignKey('user.id'))
)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    posts = db.relationship('Post', backref='author', lazy='dynamic')
    about_me = db.Column(db.String(140))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    followed = db.relationship(
        'User', secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
            digest, size)

    def follow(self, user):
        if not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user):
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user):
        return self.followed.filter(
            followers.c.followed_id == user.id).count() > 0

    def followed_posts(self):
        followed = Post.query.join(
            followers, (followers.c.followed_id == Post.user_id)).filter(
                followers.c.follower_id == self.id)
        own = Post.query.filter_by(user_id=self.id)
        return followed.union(own).order_by(Post.timestamp.desc())

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'],
            algorithm='HS256').decode('utf-8')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)


@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class Post(SearchableMixin, db.Model):
    __searchable__ = ['body']
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(140))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    language = db.Column(db.String(5))

    def __repr__(self):
        return '<Post {}>'.format(self.body)

class Songs(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    # These store the currently used lyrics for the song. part_1 stores each line, separeated
    # by ';'. part_1_ids stores the dynamodb id of each line in part_1
    part_1 = db.Column(db.String(10000))
    part_1_ids = db.Column(db.String(10000))

    # These store lines used in the custom mode in a way analagous to part_1 above
    # TODO: Storing duplicate of song in custom mode. Need fix.
    related = db.Column(db.String(10000))
    related_ids = db.Column(db.String(10000))

    # These store sentences that rhyme with the sentences stored in related
    # batches of sentence that rhyme with each sentence in related are
    # separated by ';' . Within batch, sentences are separated by '&'
    rhyme_related = db.Column(db.String(10000))
    rhyme_related_ids = db.Column(db.String(10000))

    # These are duplicate of related, rhyme_related variables to allow for threading
    related_thr = db.Column(db.String(10000))
    related_ids_thr = db.Column(db.String(10000))

    rhyme_related_thr = db.Column(db.String(10000))
    rhyme_related_ids_thr = db.Column(db.String(10000))


    # stores what song is about and similar words to what song is about
    about = db.Column(db.String(10000))

    def update_lyric(self, new_line, related=''):
        """Adds new_line to song lyrics and updates correspoding dynamodb id"""
        self.part_1 = self.part_1 + ';' + new_line[0]
        self.part_1_ids = self.part_1_ids + ';' + str(new_line[1])
        self.related = self.related + ';' + related


    def song_about(self):
        """Returns what current song is about"""
        ind = self.about.find(';')
        ind_2 = self.about.rfind('=')
        return self.about[ind_2+1:ind]


    def update_related(self, new_related, last_words, rhyming_sent, thread = False):
        """Given a list of new sentences, this function adds them to related and rhyme_related columns
        Inputs:
        new_related = list of sentences related to self.song_about() and their dynamodb ids
        last_words = list of last words of each sentence in new_related
        rhyming_sent = dictionary with last_words as keys and values are sentences that rhyme with key"""

        first_that_has_rhymes = 0
        not_yet = True
        if thread == False:
            for i in range(len(new_related)):

                # only add sentences that have rhyming sentences
                if rhyming_sent[last_words[i]] != []:
                    self.related = self.related + ';' + new_related[i][0]
                    self.update_related_id(sentence_id=int(new_related[i][1]))
                    self.update_rhyme_related(rhyming_sent[last_words[i]])
                    not_yet=False
                else:
                    if not_yet:
                        first_that_has_rhymes = i+1


        else:
            for i in range(len(new_related)):

                # only add sentences that have rhyming sentences
                if rhyming_sent[last_words[i]] != []:
                    self.related_thr = self.related_thr + ';' + new_related[i][0]
                    self.update_related_id(sentence_id=int(new_related[i][1]), thread=True)
                    self.update_rhyme_related(rhyming_sent[last_words[i]], thread=True)
                    not_yet=False
                else:
                    if not_yet:
                        first_that_has_rhymes = i+1

        return first_that_has_rhymes


    def update_rhyme_related(self, sentences, related_id = -1, thread = False):
        """Given list of sentences that rhyme with an entry of self.related, updated rhyme_related column"""

        if thread == False:
            # if we are appending at end (called from update_related())
            if related_id == -1:
                self.rhyme_related = self.rhyme_related + ';'
                self.rhyme_related_ids = self.rhyme_related_ids + ';'
                for sent in sentences:
                    self.rhyme_related = self.rhyme_related + '&' + sent[0]
                    self.update_rhyme_related_id(sentence_id=int(sent[1]))

            # TODO update an existing entry of related column

        else:
            # if we are appending at end (called from update_related())
            if related_id == -1:
                self.rhyme_related_thr = self.rhyme_related_thr + ';'
                self.rhyme_related_ids_thr = self.rhyme_related_ids_thr + ';'
                for sent in sentences:
                    self.rhyme_related_thr = self.rhyme_related_thr + '&' + sent[0]
                    self.update_rhyme_related_id(sentence_id=int(sent[1]), thread=True)

            # TODO update an existing entry of related column


    def change_related(self, related_id, new_sent, thre=False):
        """This is used in the manual edit mode. Method changes the sentence stored in related/related_thr field"""
        if not thre:
            all_index = [m.start() for m in re.finditer(';', self.related)]
            if len(all_index) == related_id + 1:
                self.related = self.related[:all_index[related_id]+1] + new_sent
            else:
                self.related = self.related[:all_index[related_id]+1] + new_sent + self.related[all_index[related_id+1]:]

        else:
            all_index = [m.start() for m in re.finditer(';', self.related_thr)]
            if len(all_index) == related_id + 1:
                self.related_thr = self.related_thr[:all_index[related_id] + 1] + new_sent
            else:
                self.related_thr = self.related_thr[:all_index[related_id] + 1] + new_sent + self.related_thr[
                                                                                     all_index[related_id + 1]:]

    def change_rhyme_related(self, rhyme_related_ids, new_sent, thre=False):
        """This is used in the manual edit mode. Method changes the sentence stored in rhyme_related/rhyme_related_thr field"""
        if not thre:
            all_index_1 = [m.start() for m in re.finditer(';', self.rhyme_related)]
            if len(all_index_1) == rhyme_related_ids[0] + 1:
                all_index_2 = [m.start() for m in re.finditer('&', self.rhyme_related[all_index_1[rhyme_related_ids[0]]+1:])]
            else:
                all_index_2 = [m.start() for m in
                               re.finditer('&', self.rhyme_related[all_index_1[rhyme_related_ids[0]]
                                                                   +1:all_index_1[rhyme_related_ids[0]+1]])]

            offset = all_index_1[rhyme_related_ids[0]]+1
            if len(all_index_2) == rhyme_related_ids[1] + 1:
                self.rhyme_related = self.rhyme_related[:offset + all_index_2[rhyme_related_ids[1]]+1] + new_sent
            else:
                self.rhyme_related = self.rhyme_related[:offset + all_index_2[rhyme_related_ids[1]]+1] + \
                                     new_sent + self.rhyme_related[offset + all_index_2[rhyme_related_ids[1]+1]:]

        else:
            return



    def clear_lyrics(self):
        """self.related is initialized as '=' to indicate we start by using self.related instead of self.related_thr
        We iterate between each having the '=' in the beggining. """
        self.part_1 = ''
        self.part_1_ids = ''
        self.related = ''
        self.related_ids = ''
        self.rhyme_related = ''
        self.rhyme_related_ids = ''

        self.related_thr = ''
        self.related_ids_thr = ''
        self.rhyme_related_thr = ''
        self.rhyme_related_ids_thr = ''

    def get_last_line(self):
        sep = self.part_1.rfind(';')

        return self.part_1[sep+1:]

    def del_last_line(self):
        sep = self.part_1.rfind(';')

        # if lyric has only one sentence
        if sep == 0:
            self.clear_lyrics()
        else:
            self.part_1 = self.part_1[:sep]

    def get_num_lines(self):
        return len([m.start() for m in re.finditer(';', self.part_1_ids)])


    def update_rhyme_related_id(self, sentence_id=-1, ind_sub_ind=[], line_being_used = -1, action='new', thread = False):
        """ Updates the dynamodb id and line_being_used id of sentences in song.related column
                Inputs:
                sentence_id = dynamodb id of sentence

                line_being_used = line in song that sentence is being used (index starts at 1)
                action = what to to with sentence
                """

        if not thread:
            # adds new sentence. this is only called from update_related
            if action == 'new':
                self.rhyme_related_ids = self.rhyme_related_ids + '&0-' + str(sentence_id)


            # updates status of sentence when sentence is added to ongoing lyrics
            elif action == 'used':
                """
                ind = [m.start() for m in re.finditer('-' + str(sentence_id), self.rhyme_related_ids)]
                for inde in ind:
                    self.rhyme_related_ids = self.rhyme_related_ids[:inde - 1] + str(line_being_used) + \
                                             self.rhyme_related_ids[inde:]
                                             """
                ind_1 = [m.start() for m in re.finditer(';', self.rhyme_related_ids)]
                ind_2 = [m.start() for m in re.finditer('&', self.rhyme_related_ids[ind_1[ind_sub_ind[0]]:])]

                self.rhyme_related_ids = self.rhyme_related_ids[:ind_1[ind_sub_ind[0]] + ind_2[ind_sub_ind[1]] + 1] \
                                         + str(line_being_used) \
                                         + self.rhyme_related_ids[ind_1[ind_sub_ind[0]]
                                                                  + ind_2[ind_sub_ind[1]] + 2:]


            # when user deletes sentence from rhyme_related_ids, we simply set its flag to 0 (as unused)
            elif action == 'del':
                """
                ind = [m.start() for m in re.finditer('-' + str(sentence_id), self.rhyme_related_ids)]
                for inde in ind:
                    self.rhyme_related_ids = self.rhyme_related_ids[:inde - 1] + '0' + \
                                             self.rhyme_related_ids[inde:]
                                             """
                ind_1 = [m.start() for m in re.finditer(';', self.rhyme_related_ids)]
                ind_2 = [m.start() for m in re.finditer('&', self.rhyme_related_ids[ind_1[ind_sub_ind[0]]:])]

                self.rhyme_related_ids = self.rhyme_related_ids[:ind_1[ind_sub_ind[0]] + ind_2[ind_sub_ind[1]] + 1] \
                                         + '0' \
                                         + self.rhyme_related_ids[ind_1[ind_sub_ind[0]]
                                                                  + ind_2[ind_sub_ind[1]] + 2:]

        else:
            # adds new sentence. this is only called from update_related
            if action == 'new':
                self.rhyme_related_ids_thr = self.rhyme_related_ids_thr + '&0-' + str(sentence_id)


            # updates status of sentence when sentence is added to ongoing lyrics
            elif action == 'used':
                """
                ind = [m.start() for m in re.finditer('-' + str(sentence_id), self.rhyme_related_ids_thr)]
                for inde in ind:
                    self.rhyme_related_ids_thr = self.rhyme_related_ids_thr[:inde - 1] + str(line_being_used) + \
                                             self.rhyme_related_ids_thr[inde:]
                                             """
                ind_1 = [m.start() for m in re.finditer(';', self.rhyme_related_ids_thr)]
                ind_2 = [m.start() for m in re.finditer('&', self.rhyme_related_ids_thr[ind_1[ind_sub_ind[0]]:])]

                self.rhyme_related_ids_thr = self.rhyme_related_ids_thr[:ind_1[ind_sub_ind[0]] + ind_2[ind_sub_ind[1]] + 1] \
                                         + str(line_being_used) \
                                         + self.rhyme_related_ids_thr[ind_1[ind_sub_ind[0]]
                                                                  + ind_2[ind_sub_ind[1]] + 2:]


            # when user deletes sentence from rhyme_related_ids, we simply set its flag to 0 (as unused)
            elif action == 'del':
                """
                ind = [m.start() for m in re.finditer('-' + str(sentence_id), self.rhyme_related_ids_thr)]
                for inde in ind:
                    self.rhyme_related_ids_thr = self.rhyme_related_ids_thr[:inde - 1] + '0' + \
                                                 self.rhyme_related_ids_thr[inde:]
                                                 """
                ind_1 = [m.start() for m in re.finditer(';', self.rhyme_related_ids_thr)]
                ind_2 = [m.start() for m in re.finditer('&', self.rhyme_related_ids_thr[ind_1[ind_sub_ind[0]]:])]

                self.rhyme_related_ids_thr = self.rhyme_related_ids_thr[
                                             :ind_1[ind_sub_ind[0]] + ind_2[ind_sub_ind[1]] + 1] \
                                             + '0' \
                                             + self.rhyme_related_ids_thr[ind_1[ind_sub_ind[0]]
                                                                          + ind_2[ind_sub_ind[1]] + 2:]


    def update_related_id(self, sentence_id=-1, id=-1, line_being_used = -1, action='new', thread = False):
        """ Updates the dynamodb id and line_being_used id of sentences in song.related column
        Inputs:
        sentence_id = dynamodb id of sentence
        id = position of sentence relative to song.related table
        line_being_used = line in song that sentence is being used (index starts at 1)
        action = what to to with sentence
        """

        if thread == False:
            all_index = [m.start() for m in re.finditer(';', self.related_ids)]

            # adds new sentence. this is only called from update_related
            if action == 'new':
                self.related_ids += ';0-' + str(sentence_id)

            # updates status of sentence when sentence is added to ongoing lyrics
            elif action == 'used':

                if len(all_index) == id + 1:
                    self.related_ids = self.related_ids[:all_index[id]+1] + str(line_being_used) + '-' + self.related_ids[all_index[id]+3:]
                else:
                    self.related_ids = self.related_ids[:all_index[id]+1] + str(line_being_used) + '-' + self.related_ids[all_index[id]+3:]

            # deletes sentence from both related and related_ids
            # TODO need to delete the corresponding rhyme_related and rhyme_related_ids
            elif action == 'del':

                all_index_related = [m.start() for m in re.finditer(';', self.related)]
                all_index_rhyme_related = [m.start() for m in re.finditer(';', self.rhyme_related)]
                all_index_rhyme_related_ids = [m.start() for m in re.finditer(';', self.rhyme_related_ids)]
                if len(all_index) == id + 1:
                    self.related_ids = self.related_ids[:all_index[id]]
                    self.related = self.related[:all_index_related[id]]
                    self.rhyme_related = self.rhyme_related[:all_index_rhyme_related[id]]
                    self.rhyme_related_ids = self.rhyme_related_ids[:all_index_rhyme_related_ids[id]]
                else:
                    self.related_ids = self.related_ids[:all_index[id]] + self.related_ids[all_index[id + 1]:]
                    self.related = self.related[:all_index_related[id]] + self.related[all_index_related[id + 1]:]
                    self.rhyme_related = self.rhyme_related[:all_index_rhyme_related[id]] +\
                                         self.rhyme_related[all_index_rhyme_related[id + 1]:]
                    self.rhyme_related_ids = self.rhyme_related_ids[:all_index_rhyme_related_ids[id]] + \
                                         self.rhyme_related_ids[all_index_rhyme_related_ids[id + 1]:]

            elif action == 'unused':
                sep = self.related_ids[all_index[id]:].find('-')
                self.related_ids = self.related_ids[:all_index[id]+1] + '0' + self.related_ids[all_index[id]+sep:]

        else:
            all_index = [m.start() for m in re.finditer(';', self.related_ids_thr)]

            # adds new sentence. this is only called from update_related
            if action == 'new':
                self.related_ids_thr += ';0-' + str(sentence_id)

            # updates status of sentence when sentence is added to ongoing lyrics
            elif action == 'used':

                if len(all_index) == id + 1:
                    self.related_ids_thr = self.related_ids_thr[:all_index[id] + 1] + str(
                        line_being_used) + '-' + self.related_ids_thr[all_index[id] + 3:]
                else:
                    self.related_ids_thr = self.related_ids_thr[:all_index[id] + 1] + str(
                        line_being_used) + '-' + self.related_ids_thr[all_index[id] + 3:]

            # deletes sentence from both related and related_ids
            elif action == 'del':

                all_index_related = [m.start() for m in re.finditer(';', self.related_thr)]
                all_index_rhyme_related = [m.start() for m in re.finditer(';', self.rhyme_related_thr)]
                all_index_rhyme_related_ids = [m.start() for m in re.finditer(';', self.rhyme_related_ids_thr)]
                if len(all_index) == id + 1:
                    self.related_ids_thr = self.related_ids_thr[:all_index[id]]
                    self.related_thr = self.related_thr[:all_index_related[id]]
                    self.rhyme_related_thr = self.rhyme_related_thr[:all_index_rhyme_related[id]]
                    self.rhyme_related_ids_thr = self.rhyme_related_ids_thr[:all_index_rhyme_related_ids[id]]
                else:
                    self.related_ids_thr = self.related_ids_thr[:all_index[id]] + self.related_ids_thr[all_index[id + 1]:]
                    self.related_thr = self.related_thr[:all_index_related[id]] + self.related_thr[all_index_related[id + 1]:]
                    self.rhyme_related_thr = self.rhyme_related_thr[:all_index_rhyme_related[id]] + \
                                         self.rhyme_related_thr[all_index_rhyme_related[id + 1]:]
                    self.rhyme_related_ids_thr = self.rhyme_related_ids_thr[:all_index_rhyme_related_ids[id]] + \
                                             self.rhyme_related_ids_thr[all_index_rhyme_related_ids[id + 1]:]


    def non_used(self, thread= False):
        """Returns sentences from related column that have not yet been used along with their local id."""

        if thread == False:
            all_index = [m.start() for m in re.finditer(';', self.related_ids)]
            non_used = []
            i = 0

            for index in all_index:

                if self.related_ids[index + 1] == '0':
                    non_used.append([self.get_related_by_id(i), i])
                i += 1

        else:
            all_index = [m.start() for m in re.finditer(';', self.related_ids_thr)]
            non_used = []
            i = 0

            for index in all_index:

                if self.related_ids_thr[index + 1] == '0':
                    non_used.append([self.get_related_by_id(i, thread=True), i])
                i += 1

        return non_used


    def num_related(self):
        """Returns the current number of related sentences"""
        return len([m.start() for m in re.finditer(';', self.related_ids)])

    def update_line(self, line_id, new_line):

        to_change = self.get_line_by_id(line_id)
        start = self.part_1.find(to_change)
        end = start + len(to_change)
        self.part_1 = self.part_1[:start] + new_line + self.part_1[end:]

    def del_line(self, line_id):

        line_id = int(line_id)

        if line_id == 0 and self.get_num_lines() == 0:
            self.clear_lyrics()

        elif line_id == self.get_num_lines() - 1:
            ind = self.part_1.rfind(';')
            self.part_1 = self.part_1[:ind]
            ind = self.part_1_ids.rfind(';')
            self.part_1_ids = self.part_1_ids[:ind]
            ind = self.related.rfind(';')
            self.related = self.related[:ind]

        else:
            to_change = self.get_line_by_id(line_id)
            start = self.part_1.find(to_change)
            end = start + len(to_change)
            self.part_1 = self.part_1[:start] + self.part_1[end+1:]

            to_change = self.get_line_id_by_id(line_id)
            start = self.part_1_ids.find(to_change)
            end = start + len(to_change)
            self.part_1_ids = self.part_1_ids[:start] + self.part_1_ids[end+1:]

            to_change = self.get_related_by_id_new(line_id)
            start = self.related.find(to_change)
            end = start + len(to_change)
            self.related = self.related[:start] + self.related[end + 1:]


    def update_line_id(self, line_id, new_id):

        to_change = self.get_line_id_by_id(line_id)
        start = self.part_1_ids.find(to_change)
        end = start + len(to_change)
        self.part_1_ids = self.part_1_ids[:start] + new_id + self.part_1_ids[end:]

    def get_line_by_id(self, line_id):

        all_index = [m.start() for m in re.finditer(';', self.part_1)]

        if len(all_index) == line_id + 1:
            return self.part_1[all_index[line_id]+1:]

        return self.part_1[all_index[line_id] + 1:all_index[line_id+1]]

    def get_related_by_id_new(self, line_id):

        all_index = [m.start() for m in re.finditer(';', self.related)]

        if len(all_index) == line_id + 1:
            return self.related[all_index[line_id]+1:]

        return self.related[all_index[line_id] + 1:all_index[line_id+1]]

    def get_line_related(self, line_id):
        all_index = [m.start() for m in re.finditer(';', self.related)]

        if len(all_index) == line_id + 1:
            return self.related[all_index[line_id] + 1:]

        return self.related[all_index[line_id] + 1:all_index[line_id + 1]]

    def get_line_id_by_id(self, line_id):
        """line_id here is the dynamodb id"""

        all_index = [m.start() for m in re.finditer(';', self.part_1_ids)]

        if len(all_index) == line_id + 1:
            return self.part_1_ids[all_index[line_id]+1:]

        return self.part_1_ids[all_index[line_id] + 1:all_index[line_id+1]]


    def get_related_id_by_line_id(self, line_id):
        #line_id is assumed to start at 1. related_id is the positional id of sentence

        # TODO Need to check if this is going to cause problems if we try to access while thread is happening
        #  TODO if it does, the idea is to return -1 and generate a new rhyming sentence.
        index_1 = self.related_ids.find(str(line_id)+'-')
        index_2 = self.related_ids_thr.find(str(line_id) + '-')

        # found in the non-thread
        if index_1 != -1:
            all_index = [m.start() for m in re.finditer(';', self.related_ids)]

            for i in range(len(all_index)):
                if all_index[i] > index_1:
                    return [i - 1, False]

            return [len(all_index) - 1, False]

        if index_2 != -1:
            all_index = [m.start() for m in re.finditer(';', self.related_ids_thr)]

            for i in range(len(all_index)):
                if all_index[i] > index_2:
                    return [i - 1, True]

            return [len(all_index) - 1, True]

        # not found in any
        if index_1 == -1 and index_2 == -1:
            return[-1,-1]

    def get_rhyme_related_id_by_line_id(self, line_id):
        #line_id is assumed to start at 1. related_id is the positional id of sentence

        # TODO Need to check if this is going to cause problems if we try to access while thread is happening
        #  TODO if it does, the idea is to return -1 and generate a new rhyming sentence.
        index_1 = self.rhyme_related_ids.find(str(line_id)+'-')
        index_2 = self.rhyme_related_ids_thr.find(str(line_id) + '-')

        # found in the non-thread
        if index_1 != -1:
            all_index = [m.start() for m in re.finditer(';', self.rhyme_related_ids)]

            for i in range(len(all_index)):
                if all_index[i] > index_1:

                    # find subindex (related to & flag)
                    all_index_2 = [m.start() for m in
                                   re.finditer('&', self.rhyme_related_ids[all_index[i - 1]:all_index[i]])]
                    for j in range(len(all_index_2)):

                        if self.rhyme_related_ids[
                           all_index_2[j] + all_index[i - 1] + 1:all_index_2[j] + all_index[i - 1] + 1 + len
                               (str(line_id))] == str(line_id):
                            return [i - 1, j, False]

            i = len(all_index)
            all_index_2 = [m.start() for m in re.finditer('&', self.rhyme_related_ids[all_index[i - 1]:])]
            for j in range(len(all_index_2)):

                if self.rhyme_related_ids[
                   all_index_2[j] + all_index[i - 1] + 1:all_index_2[j] + all_index[i - 1] + 1 + len(
                       str(line_id))] == str(line_id):
                    return [len(all_index) - 1, j, False]

        if index_2 != -1:
            all_index = [m.start() for m in re.finditer(';', self.rhyme_related_ids_thr)]

            for i in range(len(all_index)):
                if all_index[i] > index_2:

                    # find subindex (related to & flag)
                    all_index_2 = [m.start() for m in
                                   re.finditer('&', self.rhyme_related_ids_thr[all_index[i - 1]:all_index[i]])]
                    for j in range(len(all_index_2)):

                        if self.rhyme_related_ids_thr[all_index_2[j] + all_index[i - 1] + 1:
                                all_index_2[j] + all_index[i - 1] + 1 + len(str(line_id))] == str(line_id):
                            return [i - 1, j, True]

            i = len(all_index)
            all_index_2 = [m.start() for m in re.finditer('&', self.rhyme_related_ids_thr[all_index[i - 1]:])]
            for j in range(len(all_index_2)):

                if self.rhyme_related_ids_thr[all_index_2[j] + all_index[i - 1] + 1:all_index_2[j] +
                            all_index[i - 1] + 1 + len(str(line_id))] == str(line_id):
                    return [len(all_index) - 1, j, True]


    def get_rhyme_related_by_id(self, id, sub_id=-1, thresh=False):
        """sub_id is only used when we wish to avoid using a certain sentence already present in
        rhyme_related/rhyme_related_thr"""

        if not thresh:
            all_index = [m.start() for m in re.finditer(';', self.rhyme_related)]
            if id + 1 == len(all_index):
                possible_rhyme_related = self.rhyme_related[all_index[id]+1:]
            else:
                possible_rhyme_related = self.rhyme_related[all_index[id]+1: all_index[id+1]]

            all_index_2 = [m.start() for m in re.finditer(';', self.rhyme_related_ids)]
            if id + 1 == len(all_index_2):
                possible_rhyme_related_ids = self.rhyme_related_ids[all_index_2[id]+1:]
            else:
                possible_rhyme_related_ids = self.rhyme_related_ids[all_index_2[id]+1: all_index_2[id+1]]

        else:
            all_index = [m.start() for m in re.finditer(';', self.rhyme_related_thr)]
            if id + 1 == len(all_index):
                possible_rhyme_related = self.rhyme_related_thr[all_index[id] + 1:]
            else:
                possible_rhyme_related = self.rhyme_related_thr[all_index[id] + 1: all_index[id + 1]]

            all_index_2 = [m.start() for m in re.finditer(';', self.rhyme_related_ids_thr)]
            if id + 1 == len(all_index_2):
                possible_rhyme_related_ids = self.rhyme_related_ids_thr[all_index_2[id] + 1:]
            else:
                possible_rhyme_related_ids = self.rhyme_related_ids_thr[all_index_2[id] + 1: all_index_2[id + 1]]


        all_index = [m.start() for m in re.finditer('&', possible_rhyme_related)]
        all_index_2 = [m.start() for m in re.finditer('&', possible_rhyme_related_ids)]

        # flag to indicate whether same line is already
        used_elsewhere = False

        # pick sentence that has not been used
        c = 0
        id_new = -1
        for i in all_index_2:
            if possible_rhyme_related_ids[i + 1] == '0':
                id_new = c
                break
            c += 1

        # no available related word, pick random that's already used
        if id_new == -1:
            used_elsewhere = True
            id_new = random.randint(0,len(all_index_2)-1)

        if id_new + 1 == len(all_index):
            sent = possible_rhyme_related[all_index[id_new] + 1:]
            possible_rhyme_related_clean = possible_rhyme_related[:all_index[id_new]]

        else:
            sent = possible_rhyme_related[all_index[id_new] + 1: all_index[id_new + 1]]
            possible_rhyme_related_clean = possible_rhyme_related[:all_index[id_new]] + \
                                           possible_rhyme_related[all_index[id_new + 1]:]

        #TODO possible_rhyme_related_ids_clean is not correct.
        # perhaps think about finding the & symbols in the range of possible_rhyme_related and use id_new
        # to scrape the correct ..._clean
        if id_new + 1 == len(all_index_2):
            temp = possible_rhyme_related_ids[all_index_2[id_new] + 1:].find('-') + all_index_2[id_new] + 1
            sent_id = possible_rhyme_related_ids[temp + 1:]
            possible_rhyme_related_ids_clean = possible_rhyme_related_ids[:all_index_2[id_new]]

        else:
            temp = possible_rhyme_related_ids[all_index_2[id_new] + 1:].find('-') + all_index_2[id_new] + 1
            sent_id = possible_rhyme_related_ids[temp + 1: all_index_2[id_new + 1]]
            possible_rhyme_related_ids_clean = possible_rhyme_related_ids[:all_index_2[id_new]] + \
                                               possible_rhyme_related_ids[all_index_2[id_new + 1]:]

        # second part of output is to be used in jinni_implement_recom_custom (if recom == '-none-').
        return [[sent, sent_id], [possible_rhyme_related_clean, possible_rhyme_related_ids_clean], id_new, used_elsewhere]


    def get_related_by_id(self, id, thread = False):
        """Returns sentence from related column by their id
        (i.e. position within related string.  NOT dynamodb id NOR line_being_used id)"""

        if thread == False:
            all_index = [m.start() for m in re.finditer(';', self.related)]

            if len(all_index) == id + 1:
                return self.related[all_index[id]+1:]

            return self.related[all_index[id] + 1:all_index[id+1]]
        else:
            all_index = [m.start() for m in re.finditer(';', self.related_thr)]

            if len(all_index) == id + 1:
                return self.related_thr[all_index[id] + 1:]

            return self.related_thr[all_index[id] + 1:all_index[id + 1]]

    def get_related_id_by_id(self, id, thread=False):
        """related_id here corresponds to id in dynamodb"""

        if thread == False:
            all_index = [m.start() for m in re.finditer(';', self.related_ids)]
            begin = self.related_ids.find('-', all_index[id], len(self.related_ids))

            if len(all_index) == id + 1:
                return self.related_ids[begin+1:]

            return self.related_ids[begin+1:all_index[id + 1]]

        else:
            all_index = [m.start() for m in re.finditer(';', self.related_ids_thr)]
            begin = self.related_ids_thr.find('-', all_index[id], len(self.related_ids_thr))

            if len(all_index) == id + 1:
                return self.related_ids_thr[begin + 1:]

            return self.related_ids_thr[begin + 1:all_index[id + 1]]

