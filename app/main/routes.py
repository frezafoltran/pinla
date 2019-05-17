from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app
from flask_login import current_user, login_required
from flask_babel import _, get_locale
from guess_language import guess_language
from app import db
from app.main.forms import EditProfileForm, PostForm, \
   SearchForm, JinniRhymeDistanceForm, JinniCustomSong, DefZeroProb
from app.models import User, Post, Songs
from app.translate import translate
from app.main import bp
from app.rhyme_distances import dist
from app.main.sentence_generator import generate_sentence, find_suggestions, generate_sentence_lastword, \
    change_sent, sentence_related, update_syns_rank, list_of_similar_words_updated, string_to_dic, \
    populate_custom_song, synonym_scrape
from app.main.jinni_custom_song_helper import get_related
import re
import random

import time

@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        g.search_form = SearchForm()
    g.locale = str(get_locale())


@bp.route('/', methods = ['GET', 'POST'])
def main():
    return render_template('main.html')

@bp.route('/index', methods=['GET','POST'])
@login_required
def index():

    form = PostForm()
    if form.validate_on_submit():
        language = guess_language(form.post.data)
        if language == 'UNKNOWN' or len(language) > 5:
            language = ''
        post = Post(body=form.post.data, author=current_user, language=language)
        db.session.add(post)
        db.session.commit()
        flash(_('Your idea is posted!'))
        return redirect(url_for('main.index'))
    page = request.args.get('page', 1, type=int)
    posts = current_user.followed_posts().paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)

    if posts.has_next:
        next_url = url_for('main.index', page=posts.next_num)
    else:
        next_url = None

    if posts.has_prev:
        prev_url = url_for('main.index', page=posts.prev_num)
    else:
        prev_url = None

    return render_template('index.html', title=_('Home Page'), form=form, posts=posts.items, next_url=next_url, prev_url=prev_url)

@bp.route('/user/<username>')
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = user.posts.order_by(Post.timestamp.desc()).paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)


    if posts.has_next:
        next_url = url_for('main.user', username=user.username, page=posts.next_num)
    else:
        next_url = None

    if posts.has_prev:
        prev_url = url_for('main.user', username=user.username,  page=posts.prev_num)
    else:
        prev_url = None

    return render_template('user.html', user=user, posts=posts.items, next_url=next_url, prev_url=prev_url)


@bp.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash(_('Your profile changes have been saved.'))
        return redirect(url_for('main.edit_profile'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', title='Edit Profile', form=form)


@bp.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(_('User %(username) not found', username=username))
        return redirect(url_for('main.index'))

    if user == current_user:
        flash(_('You cannot follow yourself!'))
        return redirect(url_for('main.user', username=username))

    current_user.follow(user)
    db.session.commit()
    flash(_('You are now following %(username)', username=username))
    return redirect(url_for('main.user', username=username))

@bp.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash(_('User %(username) not found.', username=username))
        return redirect(url_for('main.index'))
    if user == current_user:
        flash(_('You cannot unfollow yourself!'))
        return redirect(url_for('main.user', username=username))
    current_user.unfollow(user)
    db.session.commit()
    flash(_('You are not following %(username).', username=username))
    return redirect(url_for('main.user', username=username))

@bp.route('/explore')
@login_required
def explore():
    page = request.args.get('page', 1, type=int)
    posts=Post.query.order_by(Post.timestamp.desc()).paginate(
        page, current_app.config['POSTS_PER_PAGE'], False)
    if posts.has_next:
        next_url = url_for('main.explore', page=posts.next_num)
    else:
        next_url = None

    if posts.has_prev:
        prev_url = url_for('main.explore', page=posts.prev_num)
    else:
        prev_url = None
    return render_template('index.html', title=_('Explore'), posts=posts.items, next_url=next_url, prev_url=prev_url)



@bp.route('/jinni_rhyme_distance', methods=['GET', 'POST'])
def jinni_rhyme_distance():

    form = JinniRhymeDistanceForm()
    if form.validate_on_submit():
        word_1 = form.word_1.data.lower()
        word_2 = form.word_2.data.lower()
        rhyme_at_start = form.rhyme_at_start.data
        d = dist(word_1, word_2, rhyme_at_start)

        return render_template('jinni/jinni_rhyme_distance.html', form=form, word_1=word_1, word_2=word_2, output=d)
    return render_template('jinni/jinni_rhyme_distance.html', form=form, output=-4)


@bp.route('/jinni_new_song/<song_id>/<liked>', methods=['GET', 'POST'])
def jinni_new_song(song_id, liked):

    # in case there was edit made
    if liked == '3':
        song = Songs.query.filter_by(id=song_id).first()
        lyric_clean = song.part_1.split(';')[1:]

        ids = song.part_1_ids.split(';')[1:]

        if len(song.part_1) >= 400:
            return render_template('jinni/jinni_new_song.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=1)
        else:
            return render_template('jinni/jinni_new_song.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=0)

    song = Songs.query.filter_by(id=song_id).first()
    lyric_clean = song.part_1.split(';')[1:]

    first_sentence = song.part_1.split(';')[1:]
    ids = song.part_1_ids.split(';')[1:]
    song_len = len(song.part_1)

    # stops if too many lines were produced
    if song_len >= 400:

        return render_template('jinni/jinni_new_song.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=1)


    # liked = 2 corresponds to initialization of song
    if liked != '2':

        # Makes pattern each pair of sentence rhymes
        curr_line = song.get_num_lines()
        if curr_line % 2 == 0:
            new_sentence = generate_sentence()
        else:
            last_sent = song.get_last_line()
            new_sentence = generate_sentence(last_sent)

        #song.update_lyric(new_sentence[0])
        #song.update_ids(str(new_sentence[1]))
        song.update_lyric(new_sentence)
        db.session.commit()
        lyric_clean = song.part_1.split(';')[1:]
        ids = song.part_1_ids.split(';')[1:]

        return render_template('jinni/jinni_new_song.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=0)

    return render_template('jinni/jinni_new_song.html', lyric=first_sentence, song_id=song_id, ids=ids, end=0)


@bp.route('/jinni_new_song_custom/<song_id>/<liked>', methods=['GET', 'POST'])
def jinni_new_song_custom(song_id, liked):


    # TODO in case there was edit made
    if liked == '3':
        song = Songs.query.filter_by(id=song_id).first()
        lyric_clean = song.part_1.split(';')[1:]

        ids = song.part_1_ids.split(';')[1:]
        about = song.about.split(';')[0]
        if len(song.part_1) >= 400:
            return render_template('jinni/jinni_new_song_custom.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=1, about=about)
        else:
            return render_template('jinni/jinni_new_song_custom.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=0, about=about)

    song = Songs.query.filter_by(id=song_id).first()
    about = song.song_about()
    lyric_clean = song.part_1.split(';')[1:]

    first_sentence = song.part_1.split(';')[1:]
    ids = song.part_1_ids.split(';')[1:]
    song_len = len(song.part_1)

    # stops if too many lines were produced
    if song_len >= 400:

        return render_template('jinni/jinni_new_song_custom.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=1, about=about)


    # liked = 2 corresponds to initialization of song
    if liked != '2':

        print('related: ', song.related)
        print('related_ids: ', song.related_ids)
        print('rhyme_related: ', song.rhyme_related)
        print('rhyme_related_ids: ', song.rhyme_related_ids)
        print('related_thr: ', song.related_thr)
        print('related_ids_thr: ', song.related_ids_thr)
        print('rhyme_related_thr: ', song.rhyme_related_thr)
        print('rhyme_related_ids_thr: ', song.rhyme_related_ids_thr)


        curr_line = song.get_num_lines()
        if curr_line % 2 == 0:

            # indicates self.related is currently being used
            if song.about[0] == '=':
                thread_bool = False
            # if song.related_thr is currently used
            else:
                thread_bool = True

            # non_used is a list of the non-used sentences in related or related_thr
            non_used = song.non_used(thread=thread_bool)
            new_sentence = get_related(non_used, song.id, curr_line, thread=thread_bool)

        else:

            # gets id of previous line along with whether it belongs to related or related_thr
            [related_id, thre] = song.get_related_id_by_line_id(curr_line)

            # gets new sentence that agrees with above
            [new_sentence, temp_discard] = song.get_rhyme_related_by_id(related_id, thre)

            # updates sentence status:
            song.update_rhyme_related_id(sentence_id=new_sentence[1], line_being_used=curr_line+1, action='used', thread=thre)

        # TODO Check why new_sentence is empty in some cases
        if new_sentence:
            song.update_lyric(new_sentence)

        db.session.commit()
        lyric_clean = song.part_1.split(';')[1:]
        ids = song.part_1_ids.split(';')[1:]

        return render_template('jinni/jinni_new_song_custom.html', lyric=lyric_clean, song_id=song_id, ids=ids, end=0, about=about)

    synonyms = synonym_scrape(song.song_about())

    return render_template('jinni/jinni_new_song_custom.html', lyric=first_sentence, song_id=song_id, ids=ids, end=0, about=about, syn=synonyms)

@bp.route('/jinni_line_edit_custom/<song_id>/<line_id>', methods=['GET', 'POST'])
def jinni_line_edit_custom(song_id, line_id):

    song_id = int(song_id)
    line_id = int(line_id)

    curr_song = Songs.query.filter_by(id=song_id).first()
    lyrics = curr_song.part_1

    all_index = [m.start() for m in re.finditer(';', lyrics)]

    if len(all_index) == line_id + 1:
        curr_line = lyrics[all_index[line_id] + 1:]
    else:
        curr_line = lyrics[all_index[line_id]+1:all_index[line_id+1]]

    try:
        prec_line = lyrics[all_index[line_id-1]:all_index[line_id]]
    except IndexError:
        prec_line = ''

    try:
        suc_line = lyrics[all_index[line_id+1]:all_index[line_id+2]]
    except IndexError:
        suc_line = ''


    # find new suggestions for line
    suggestions = find_suggestions(prec_line, suc_line, curr_line)
    suggestions = [[suggestions[0][0], str(suggestions[0][1])], [suggestions[1][0], str(suggestions[1][1])]]

    return render_template('jinni/jinni_line_edit.html', suggestions=suggestions, song_id=song_id, line_id=line_id)

@bp.route('/jinni_line_edit/<song_id>/<line_id>', methods=['GET', 'POST'])
def jinni_line_edit(song_id, line_id):

    song_id = int(song_id)
    line_id = int(line_id)

    curr_song = Songs.query.filter_by(id=song_id).first()
    lyrics = curr_song.part_1

    all_index = [m.start() for m in re.finditer(';', lyrics)]

    if len(all_index) == line_id + 1:
        curr_line = lyrics[all_index[line_id] + 1:]
    else:
        curr_line = lyrics[all_index[line_id]+1:all_index[line_id+1]]

    try:
        prec_line = lyrics[all_index[line_id-1]:all_index[line_id]]
    except IndexError:
        prec_line = ''

    try:
        suc_line = lyrics[all_index[line_id+1]:all_index[line_id+2]]
    except IndexError:
        suc_line = ''


    # find new suggestions for line
    suggestions = find_suggestions(prec_line, suc_line, curr_line)
    suggestions = [[suggestions[0][0], str(suggestions[0][1])], [suggestions[1][0], str(suggestions[1][1])]]

    return render_template('jinni/jinni_line_edit.html', suggestions=suggestions, song_id=song_id, line_id=line_id)

@bp.route('/jinni_implement_recom_custom/<recom>/<song_id>/<line_id>', methods=['GET', 'POST'])
def jinni_implement_recom_custom(recom, song_id, line_id):

    song = Songs.query.filter_by(id=song_id).first()
    # line_id starts at 0
    line_id = int(line_id)

    # if no recomendation was passed, generate new sentence based on line being changed (for now)
    if recom == '-none-':

        # sentence must match in meaning with song.about and rhyme with succeding sentence
        if line_id % 2 == 0:

            # need to find where curr_sent is stored. There are two possibilities, related, related_thr,
            # Then we pick a corresponding sentence in rhyme_related/rhyme_related_thr
            # then we delete (mark as unused) the added sentence from rhyme_related_thr/rhyme_related and add it
            # to related/related_thr.
            # further, we copy the elements from the same rhyme_related/rhyme_related_thr class in to the new
            # rhyme_related/rhyme_related_thr class correspondent to the added sentence

            [related_id, thre] = song.get_related_id_by_line_id(line_id+1)

            print('related_id: ', related_id)

            # gets new sentence that agrees with above
            # TODO If there's not enough sentences in the corresponding rhyme_related/rhyme_related_thr, this will return -1
            # TODO if this happens, but there's more than one sentence in rhyme_related/rhyme_related_thr, we just pick
            # a sentence that is different from related_id (need to change get_rhyme_related_by_id). If there's only one
            # sentence and its currently used, we do not wish this to happen (need to implement a check when sentence is first added to song)
            try:
                [new_sentence, [possible_rhyme_related, possible_rhyme_related_ids]] = song.get_rhyme_related_by_id(related_id, thre)
                if thre:
                    song.related_thr += ';' + new_sentence[0]
                    song.related_ids_thr += ';' + str(line_id + 1) + '-' + new_sentence[1]
                    song.rhyme_related_thr += ';' + possible_rhyme_related
                    song.rhyme_related_ids_thr += ';' + possible_rhyme_related_ids
                else:
                    song.related += ';' + new_sentence[0]
                    song.related_ids += ';' + str(line_id + 1) + '-' + new_sentence[1]
                    song.rhyme_related += ';' + possible_rhyme_related
                    song.rhyme_related_ids += ';' + possible_rhyme_related_ids
            except ValueError:
                new_sentence = generate_sentence(song.get_line_by_id(line_id))


            db.session.commit()

            print('related: ', song.related)
            print('related_ids: ', song.related_ids)
            print('rhyme_related: ', song.rhyme_related)
            print('rhyme_related_ids: ', song.rhyme_related_ids)
            print('related_thr: ', song.related_thr)
            print('related_ids_thr: ', song.related_ids_thr)
            print('rhyme_related_thr: ', song.rhyme_related_thr)
            print('rhyme_related_ids_thr: ', song.rhyme_related_ids_thr)

        # TODO
        else:
            #prev_sent = song.get_line_by_id(line_id - 1)
            new_sentence = ['test', -1]

        song.update_line_id(line_id, str(new_sentence[1]))
        song.update_line(line_id, new_sentence[0])
        db.session.commit()

    # recom comes from database
    elif recom.find('!-!') != -1:
        sent = recom[:recom.find('!-!')]
        id = recom[recom.find('!-!') + 2:]
        print(id)
        song.update_line_id(line_id, str(id))
        song.update_line(line_id, sent)
        db.session.commit()

    # recom comes from edit field
    else:
        old_id = song.get_line_id_by_id(line_id)

        # if edit was made by developer (marked by including (-commit-) at end of sentence)
        # we commit changes to database (i.e. this is made to correct sentences)
        dev_mark = recom.find('(-commit-)')
        flash(dev_mark)
        if dev_mark != -1:

            # Only commit change if last word did not change
            recom_new = recom[:dev_mark]

            if len(recom_new) <= 40:
                new_last_word = recom_new.strip().split(' ')[-1]

                old_last_word = song.get_line_by_id(line_id)
                old_last_word = old_last_word.strip().split(' ')[-1]

                if new_last_word == old_last_word:
                    change_sent(recom_new, int(old_id))

                song.update_line_id(line_id, str(old_id))
                song.update_line(line_id, recom_new)
                db.session.commit()

            else:
                flash('New sentence is too long.')
        else:

            if len(recom) <= 40:
                song.update_line_id(line_id, str(old_id))
                song.update_line(line_id, recom)
                db.session.commit()
            else:
                flash('New sentence is too long.')

    return redirect(url_for('main.jinni_new_song_custom', song_id=song_id, liked=3))

@bp.route('/jinni_use_syn/<song_id>/<syn>')
def jinni_use_syn(song_id, syn):

    song = Songs.query.filter_by(id=song_id).first()
    song.clear_lyrics()
    req_word = syn

    # format string of similar words
    syns = list_of_similar_words_updated(req_word)
    song.about = '==' + req_word + ';' + str(syns[0]) + ';' + str(syns[1])
    db.session.commit()

    # populate the field related_thr and rhyme_related_thr by using thread
    populate_custom_song(syns, song.id)

    populate_custom_song(syns, song.id, thread=False, first=True)

    return render_template('jinni/jinni_main_waiting.html', song=song)


@bp.route('/jinni_implement_recom/<recom>/<song_id>/<line_id>', methods=['GET', 'POST'])
def jinni_implement_recom(recom, song_id, line_id):

    song = Songs.query.filter_by(id=song_id).first()
    line_id = int(line_id)

    # if no recomendation was passed, generate new sentence based on line being changed (for now)
    if recom == '-none-':
        recom_new = generate_sentence(song.get_line_by_id(line_id))
        song.update_line_id(line_id, str(recom_new[1]))
        song.update_line(line_id, recom_new[0])
        db.session.commit()

    # recom comes from database
    elif recom.find('!-!') != -1:
        sent = recom[:recom.find('!-!')]
        id = recom[recom.find('!-!') + 2:]
        print(id)
        song.update_line_id(line_id, str(id))
        song.update_line(line_id, sent)
        db.session.commit()

    # recom comes from edit field
    else:
        old_id = song.get_line_id_by_id(line_id)

        # if edit was made by developer (marked by including (-commit-) at end of sentence)
        # we commit changes to database (i.e. this is made to correct sentences)
        dev_mark = recom.find('(-commit-)')
        flash(dev_mark)
        if dev_mark != -1:

            # Only commit change if last word did not change
            recom_new = recom[:dev_mark]

            if len(recom_new) <= 40:
                new_last_word = recom_new.strip().split(' ')[-1]

                old_last_word = song.get_line_by_id(line_id)
                old_last_word = old_last_word.strip().split(' ')[-1]

                if new_last_word == old_last_word:
                    change_sent(recom_new, int(old_id))

                song.update_line_id(line_id, str(old_id))
                song.update_line(line_id, recom_new)
                db.session.commit()

            else:
                flash('New sentence is too long.')
        else:

            if len(recom) <= 40:
                song.update_line_id(line_id, str(old_id))
                song.update_line(line_id, recom)
                db.session.commit()
            else:
                flash('New sentence is too long.')

    return redirect(url_for('main.jinni_new_song', song_id=song_id, liked=3))

@bp.route('/jinni_publish_song/<song_id>', methods=['GET', 'POST'])
def jinni_publish_song(song_id):

    song = Songs.query.filter_by(id=song_id).first()
    update_syns_rank(song.about, song.part_1)
    return render_template('jinni/jinni_publish_song.html')


@bp.route('/jinni_main', methods=['GET', 'POST'])
def jinni_main():

    custom_song_form = JinniCustomSong()

    synonyms = []
    if custom_song_form.is_submitted():
        synonyms = synonym_scrape(custom_song_form.req_word.data)

    song = Songs(part_1='', part_1_ids='')
    db.session.add(song)
    song.clear_lyrics()
    first_sentence = generate_sentence()
    song.update_lyric(first_sentence)
    db.session.commit()

    if custom_song_form.validate_on_submit():

        song.clear_lyrics()
        req_word = custom_song_form.req_word.data.lower()

        #format string of similar words
        syns = list_of_similar_words_updated(req_word)
        song.about = '==' + req_word + ';' + str(syns[0]) + ';' + str(syns[1])
        db.session.commit()

        # populate the field related_thr and rhyme_related_thr by using thread
        populate_custom_song(syns, song.id)

        populate_custom_song(syns, song.id, thread=False, first=True)

        return render_template('jinni/jinni_main_waiting.html', song=song)
        #return redirect(url_for('main.jinni_new_song_custom', liked=2, song_id=song.id))

    return render_template('jinni/jinni_main.html', curr_song=song, custom_song_form=custom_song_form, synonyms=synonyms)

@bp.route('/rn_main', methods=['GET', 'POST'])
def rn_main():
    def_zero_prob_form = DefZeroProb()

    if def_zero_prob_form.validate_on_submit():
        full = 'rn_plots/n' + str(def_zero_prob_form.n.data) + '_full.png'
        zoomed = 'rn_plots/n' + str(def_zero_prob_form.n.data) + '_thresh.png'
        return render_template('reaction_networks/rn_plot.html', full=full, zoomed=zoomed)

    return render_template('reaction_networks/rn_main.html', rn_form = def_zero_prob_form)

@bp.route('/translate', methods=['POST'])
@login_required
def translate_text():
    return jsonify({'text': translate(request.form['text'],
                                      request.form['source_language'],
                                      request.form['dest_language'])})

@bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        g.search_form = SearchForm()
    g.locale = str(get_locale())

@bp.route('/search')
@login_required
def search():
    if not g.search_form.validate():
        return redirect(url_for('main.explore'))
    page = request.args.get('page', 1, type=int)
    posts, total = Post.search(g.search_form.q.data, page,
                               current_app.config['POSTS_PER_PAGE'])

    next_url = url_for('main.search', q=g.search_form.q.data, page=page + 1) \
        if total > page * current_app.config['POSTS_PER_PAGE'] else None
    prev_url = url_for('main.search', q=g.search_form.q.data, page=page - 1) \
        if page > 1 else None
    return render_template('search.html', title=_('Search'), posts=posts,
                           next_url=next_url, prev_url=prev_url)

@bp.route('/user/<username>/popup')
@login_required
def user_popup(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template('user_popup.html', user=user)