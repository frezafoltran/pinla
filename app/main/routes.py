from datetime import datetime
from flask import render_template, flash, redirect, url_for, request, g, \
    jsonify, current_app
from flask_login import current_user, login_required
from flask_babel import _, get_locale
from guess_language import guess_language
from app import db
from app.main.forms import EditProfileForm, PostForm, \
   SearchForm, JinniRhymeDistanceForm, JinniCustomSong, DefZeroProb, JinniBlankCanvasForm
from app.models import User, Post, Songs
from app.translate import translate
from app.main import bp
from app.rhyme_distances import dist
from app.main.sentence_generator import generate_sentence, find_suggestions, generate_sentence_lastword, \
    change_sent, sentence_related, update_syns_rank, list_of_similar_words_updated, string_to_dic, \
    populate_custom_song, synonym_scrape, get_sent_with_rhyme, get_sent
from app.main.jinni_custom_song_helper import get_related
import re
import random
import time
import boto3

dynamodb = boto3.resource("dynamodb")
rhyme_table = dynamodb.Table("Rhyme")

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


@bp.route('/jinni_use_syn/<syn>/<rhyme_with_line>/<song_id>', methods=['GET', 'POST'])
def jinni_use_syn(syn, rhyme_with_line, song_id):


    if rhyme_with_line != '-1':

        song = Songs.query.filter_by(id=song_id).first()

        try:
            rhyme_with_line_int = int(rhyme_with_line)
            is_int = True
        except ValueError:
            is_int = False

        if is_int:

            if rhyme_with_line != '-2':
                sent = song.get_line_by_id(rhyme_with_line_int - 1)
                rhyme_word = sent.strip(' ').split(' ')[-1]

            else:
                rhyme_word = ''

        else:
            rhyme_word = rhyme_with_line
            if syn == '-1':
                syn = ''


        new_sent = get_sent(word=syn, rhyme=rhyme_word)

        if new_sent != 1:

            song.update_lyric(new_sent, syn)
            db.session.commit()

        return redirect(url_for('main.jinni_blank_canvas', song_id=song.id))



    song = Songs(part_1='', part_1_ids='')
    db.session.add(song)
    song.clear_lyrics()
    song.about = syn
    db.session.commit()
    song.clear_lyrics()

    new_sent = get_sent(word=syn)

    song.update_lyric(new_sent, syn)
    db.session.commit()

    return redirect(url_for('main.jinni_blank_canvas', song_id=song.id))


@bp.route('/jinni_implement_recom/<recom>/<song_id>/<line_id>', methods=['GET', 'POST'])
def jinni_implement_recom(recom, song_id, line_id):

    song = Songs.query.filter_by(id=song_id).first()
    line_id = int(line_id)

    # if no recomendation was passed, generate new sentence based on line being changed (for now)
    if recom == '-none-':

        rhyme = song.get_line_by_id(line_id)
        rhyme = rhyme.strip(' ').split(' ')[-1]
        related = song.get_line_related(line_id)

        recom_new = get_sent(word=related, rhyme=rhyme)

        if recom_new == 1:
            lyric_clean = song.part_1.split(';')[1:]
            blank_canvas_form = JinniBlankCanvasForm()
            return render_template('jinni/jinni_blank_canvas.html', new_line_form=blank_canvas_form,
                                   lyric=lyric_clean, song=song, end=0, timeout=1)

        song.update_line_id(line_id, str(recom_new[1]))
        song.update_line(line_id, recom_new[0])
        db.session.commit()

    # recom comes from database
    elif recom.find('!-!') != -1:
        sent = recom[:recom.find('!-!')]
        id = recom[recom.find('!-!') + 2:]

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

    return redirect(url_for('main.jinni_blank_canvas', song_id=song.id))

@bp.route('/jinni_publish_song/<song_id>', methods=['GET', 'POST'])
def jinni_publish_song(song_id):

    song = Songs.query.filter_by(id=song_id).first()
    #update_syns_rank(song.about, song.part_1)
    return render_template('jinni/jinni_publish_song.html')


@bp.route('/jinni_main', methods=['GET', 'POST'])
def jinni_main():

    custom_song_form = JinniCustomSong()

    synonyms = []
    if custom_song_form.is_submitted():
        synonyms = synonym_scrape(custom_song_form.req_word.data)

    if custom_song_form.validate_on_submit():


        req_word = custom_song_form.req_word.data.lower()
        song = Songs(part_1='', part_1_ids='')
        db.session.add(song)
        song.clear_lyrics()

        first_sent = get_sent(word=req_word)

        song.update_lyric(first_sent, req_word)
        song.about = req_word
        db.session.commit()

        return redirect(url_for('main.jinni_blank_canvas', song_id=song.id))

    return render_template('jinni/jinni_main.html', custom_song_form=custom_song_form, synonyms=synonyms)

@bp.route('/jinni_blank_canvas/<song_id>/', methods=['GET', 'POST'])
def jinni_blank_canvas(song_id):

    song = Songs.query.filter_by(id=song_id).first()
    blank_canvas_form = JinniBlankCanvasForm(req_word=song.about, rhyme_with_line=1)
    lyric_clean = song.part_1.split(';')[1:]
    synonyms = []
    synonyms_rhyme = []
    rhyme_with_line = -1
    new_sent = -1
    req_word_allowed = True
    req_rhyme_allowed = True

    if song.get_num_lines() >= 18:
        return render_template('jinni/jinni_blank_canvas.html', new_line_form=blank_canvas_form, lyric=lyric_clean,
                               song=song, end=1, timeout=0)

    if blank_canvas_form.is_submitted():

        try:
            rhyme_with_line_int = int(blank_canvas_form.rhyme_with_line.data)
            is_int = True
        except ValueError:
            is_int = False

        # checks if req_word is in database
        if blank_canvas_form.req_word.data:
            try:
                response = rhyme_table.get_item(
                    Key={
                        'id': str(blank_canvas_form.req_word.data).lower()
                    }
                )

                response['Item']['rhymes']
                req_word_allowed = True

            except KeyError:
                blank_canvas_form.req_word.errors = [str(blank_canvas_form.req_word.data) +
                                                     ' is not currently in the database']
                synonyms = synonym_scrape(blank_canvas_form.req_word.data.lower())
                req_word_allowed = False
                rhyme_with_line = -2

        if blank_canvas_form.rhyme_with_line.data and not is_int:

            try:
                response = rhyme_table.get_item(
                    Key={
                        'id': blank_canvas_form.rhyme_with_line.data.lower()
                    }
                )

                response['Item']['rhymes']
                req_rhyme_allowed = True

            except KeyError:
                blank_canvas_form.rhyme_with_line.errors = [str(blank_canvas_form.rhyme_with_line.data) +
                                                            ' is not currently in the database']
                synonyms_rhyme = synonym_scrape(blank_canvas_form.rhyme_with_line.data.lower())
                req_rhyme_allowed = False

        print(req_rhyme_allowed)
        print(req_word_allowed)
        if not req_word_allowed or not req_rhyme_allowed:
            print('---------------here')
            lyric_clean = song.part_1.split(';')[1:]
            return render_template('jinni/jinni_blank_canvas.html', new_line_form=blank_canvas_form,
                                   lyric=lyric_clean,
                                   song=song, synonyms=synonyms, synonyms_rhyme=synonyms_rhyme,
                                   rhyme_with_line=rhyme_with_line, end=0, timeout=0)


        if is_int:
            # check if input is in range
            if rhyme_with_line_int > song.get_num_lines():
                blank_canvas_form.rhyme_with_line.errors = ['This must match one of the current lines in song.']

            elif rhyme_with_line_int <= 0:
                blank_canvas_form.rhyme_with_line.errors = ['This must be a positive integer.']

            # rhyme_with_line is within range
            else:
                sent = song.get_line_by_id(rhyme_with_line_int - 1)
                rhyme_word = sent.strip(' ').split(' ')[-1]

                # check if req_word is in database
                if blank_canvas_form.req_word.data and req_word_allowed:
                    new_sent = get_sent(word=str(blank_canvas_form.req_word.data).lower(),
                                                       rhyme=rhyme_word)
                # generate sentence based only on rhyme
                else:
                    new_sent = get_sent(rhyme=rhyme_word)

        else:
            if blank_canvas_form.rhyme_with_line.data:

                if blank_canvas_form.req_word.data and req_word_allowed:
                    if req_rhyme_allowed:
                        new_sent = get_sent(word=str(blank_canvas_form.req_word.data).lower(),
                                                           rhyme=str(blank_canvas_form.rhyme_with_line.data).lower())

                # TODO maybe delete this
                else:
                    if req_rhyme_allowed:
                        new_sent = get_sent(rhyme=str(blank_canvas_form.rhyme_with_line.data).lower())

            else:
                if blank_canvas_form.req_word.data and req_word_allowed:
                    new_sent = get_sent(word=str(blank_canvas_form.req_word.data).lower())

                elif not blank_canvas_form.req_word.data:
                    new_sent = get_sent(word=str())

        # timeout
        if new_sent == 1:
            if not synonyms:
                synonyms = synonym_scrape(blank_canvas_form.req_word.data.lower())

            return render_template('jinni/jinni_blank_canvas.html', new_line_form=blank_canvas_form,
                                   lyric=lyric_clean,
                                   song=song, synonyms=synonyms, synonyms_rhyme=synonyms_rhyme,
                                   rhyme_with_line=rhyme_with_line, end=0, timeout=1)


        if new_sent != -1:
            if not blank_canvas_form.req_word.data or not req_word_allowed:
                related = '-'
            else:
                related = blank_canvas_form.req_word.data.lower()

            song.update_lyric(new_sent, related)
            db.session.commit()

        lyric_clean = song.part_1.split(';')[1:]
        return render_template('jinni/jinni_blank_canvas.html', new_line_form=blank_canvas_form,
                               lyric=lyric_clean,
                               song=song, synonyms=synonyms, synonyms_rhyme=synonyms_rhyme,
                               rhyme_with_line=rhyme_with_line, end=0, timeout=0)


    return render_template('jinni/jinni_blank_canvas.html', new_line_form=blank_canvas_form, lyric=lyric_clean,
                           song=song, end=0, timeout=0)

@bp.route('/rn_main', methods=['GET', 'POST'])
def rn_main():
    def_zero_prob_form = DefZeroProb()

    if def_zero_prob_form.validate_on_submit():
        full = 'rn_plots/n' + str(def_zero_prob_form.n.data) + '_full.png'
        zoomed = 'rn_plots/n' + str(def_zero_prob_form.n.data) + '_thresh.png'
        return render_template('reaction_networks/rn_plot.html', full=full, zoomed=zoomed)

    return render_template('reaction_networks/rn_main.html', rn_form=def_zero_prob_form)

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