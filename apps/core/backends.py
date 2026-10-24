from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    """Permite ingresar el usuario sin distinguir mayúsculas (p. ej. «Admin» = «admin»).

    La contraseña sí distingue mayúsculas.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        username = username.strip()
        user = User.objects.filter(username__iexact=username).order_by("id").first()
        if user is None:
            User().set_password(password)  # mismo costo de tiempo que un login válido
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
