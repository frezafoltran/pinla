from flask import request
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, IntegerField
from wtforms.validators import ValidationError, DataRequired, Length
from flask_babel import _, lazy_gettext as _l
from app.models import User
import boto3

dynamodb = boto3.resource("dynamodb")
rhyme_table = dynamodb.Table("Rhyme")

class EditProfileForm(FlaskForm):
    username = StringField(_l('Username'), validators=[DataRequired()])
    about_me = TextAreaField(_l('About me'), validators=[Length(min=0, max=140)])
    submit = SubmitField(_l('Submit'))

    def __init__(self, original_username, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=self.username.data).first()

            if user is not None:
                raise ValidationError(_('This username is already being used. Please use a different one.'))

class PostForm(FlaskForm):
    post = TextAreaField(_l('Share an Idea'), validators=[DataRequired(), Length(min=1, max=140)])
    submit = SubmitField(_l('Submit'))



class JinniRhymeDistanceForm(FlaskForm):

    word_1 = StringField(_l('First word'), validators=[DataRequired()])
    word_2 = StringField(_l('Second word'), validators=[DataRequired()])
    rhyme_at_start = BooleanField('Front-word rhyme')
    submit = SubmitField(_l('Get distance!'))


class JinniCustomSong(FlaskForm):

    req_word = StringField(_l('Enter a topic of your choice'), validators=[DataRequired()])
    submit = SubmitField(_l('Create a Song!'))

    # TODO validator not working!
    def validate_req_word(self, req_word):

        req_word = str(req_word.data).lower()
        try:
            response = rhyme_table.get_item(
                Key={
                    'id': req_word
                }
            )
            return response['Item']['rhymes']
        except KeyError:
            raise ValidationError(req_word + ' is not currently in the database')

class DefZeroProb(FlaskForm):

    n = IntegerField(_l('Number of distinct species in network:'), validators=[DataRequired()])
    submit = SubmitField(_l('Plot results'))


class SearchForm(FlaskForm):
    q = StringField(_l('Search'), validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        if 'formdata' not in kwargs:
            kwargs['formdata'] = request.args
        if 'csrf_enabled' not in kwargs:
            kwargs['csrf_enabled'] = False
        super(SearchForm, self).__init__(*args, **kwargs)