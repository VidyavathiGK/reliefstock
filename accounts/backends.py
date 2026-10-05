from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Allows users to authenticate with either their username OR their email address,
    case-insensitively, and automatically trims accidental leading/trailing whitespace.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or not password:
            return None

        clean_username = str(username).strip()

        try:
            user = UserModel.objects.filter(
                Q(username__iexact=clean_username) | Q(email__iexact=clean_username)
            ).first()
        except UserModel.DoesNotExist:
            return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
