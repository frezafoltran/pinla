from app import db
from app.models import Songs
import random
from app.main.sentence_generator import populate_custom_song, string_to_dic


def get_related(non_used, song_id, curr_line, thread):

    song = Songs.query.filter_by(id=song_id).first()
    new_sentence = []

    # pick random sentence from local related database
    if len(non_used) > 0:
        indexes = [item[1] for item in non_used]
        picked = random.choice(indexes)
        sentence = song.get_related_by_id(picked, thread=thread)
        id = song.get_related_id_by_id(picked, thread=thread)
        new_sentence = [sentence, id]
        song.update_related_id(id=picked, action='used', line_being_used=curr_line + 1, thread=thread)
        db.session.commit()

    # if there are no more sentences in related/related_thr, pick random sentence from the other,
    # re-populate related using threading and change the '=' mark to indicate currently
    # using related_thr
    else:

        # repopulate related
        populate_custom_song(string_to_dic(song.about), song.id, thread=thread)

        # change current database we use
        if not thread:
            song.about = song.about[1:]
            #song.about_thr = '=' + song.about_thr
        else:
            #song.about_thr = song.about_thr[1:]
            song.about = '=' + song.about

        db.session.commit()


        non_used = song.non_used(thread=not thread)
        if len(non_used) > 0:
            indexes = [item[1] for item in non_used]
            picked = random.choice(indexes)
            sentence = song.get_related_by_id(picked, thread=not thread)
            id = song.get_related_id_by_id(picked, thread=not thread)
            new_sentence = [sentence, id]
            song.update_related_id(id=picked, action='used', line_being_used=curr_line + 1, thread=not thread)
            db.session.commit()

    return new_sentence
