from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from apps.core.crud import Column, HRCreateView, HRDeleteView, HRListView, HRUpdateView
from apps.core.forms import DATETIME, BaseModelForm
from apps.core.modules import Module

from .models import Announcement


class AnnouncementForm(BaseModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "body", "pinned", "departments", "publish_at", "expires_at"]
        widgets = {"publish_at": DATETIME, "expires_at": DATETIME, "body": forms.Textarea(attrs={"rows": 8}),
                   "departments": forms.CheckboxSelectMultiple}


class AnnouncementList(HRListView):
    model = Announcement
    module = Module.ANUNCIOS
    url_prefix = "anuncios:anuncio"
    title = "Anuncios"
    create_label = "Nuevo anuncio"
    template_name = "anuncios/list.html"
    search_fields = ["title", "body"]
    paginate_by = 10
    columns = [Column("Título", "title"), Column("Publicado", "publish_at"), Column("Autor", "created_by")]

    def get_queryset(self):
        from apps.core.modules import Level

        if self.request.user.can(Module.ANUNCIOS, Level.EDITAR):
            return super().get_queryset().select_related("created_by")
        return Announcement.visible_for(self.request.user).select_related("created_by")


class AnnouncementCreate(HRCreateView):
    model = Announcement
    form_class = AnnouncementForm
    module = Module.ANUNCIOS
    url_prefix = "anuncios:anuncio"


class AnnouncementUpdate(HRUpdateView):
    model = Announcement
    form_class = AnnouncementForm
    module = Module.ANUNCIOS
    url_prefix = "anuncios:anuncio"


class AnnouncementDelete(HRDeleteView):
    model = Announcement
    module = Module.ANUNCIOS
    url_prefix = "anuncios:anuncio"


@login_required
def announcement_detail(request, pk):
    obj = get_object_or_404(Announcement.visible_for(request.user), pk=pk)
    return render(request, "anuncios/detail.html", {"obj": obj})
