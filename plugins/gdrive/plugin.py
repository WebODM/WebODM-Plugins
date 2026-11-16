from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect
from django.utils.translation import gettext as _

from app.plugins import PluginBase, Menu, MountPoint
from .api import ImportFiles

CONFIG_KEYS = ('client_id', 'api_key')

class SettingsForm(forms.Form):
    client_id = forms.CharField(label=_("OAuth Client ID"), required=False, max_length=512)
    api_key = forms.CharField(label=_("API Key"), required=False, max_length=512)

class Plugin(PluginBase):
    def include_js_files(self):
        return ['main.js']

    def include_css_files(self):
        return ['main.css']

    def build_jsx_components(self):
        return ['GDriveSource.jsx']

    def main_menu(self):
        return [Menu(_("Google Drive"), self.public_url(""), "fab fa-google-drive fa-fw", admin_only=True)]

    def get_config(self):
        ds = self.get_global_data_store()
        return {k: ds.get_string(k) for k in CONFIG_KEYS}

    def app_mount_points(self):
        @user_passes_test(lambda u: u.is_superuser)
        def settings_view(request):
            if request.method == 'POST':
                form = SettingsForm(request.POST)
                if form.is_valid():
                    ds = self.get_global_data_store()
                    for k in CONFIG_KEYS:
                        ds.set_string(k, form.cleaned_data[k].strip())
                    messages.success(request, _("Settings updated."))
                    return redirect(self.public_url(""))
            else:
                form = SettingsForm(initial=self.get_config())

            return render(request, self.template_path("settings.html"), {
                'title': _('Google Drive'),
                'form': form,
                'origin': request.build_absolute_uri('/').rstrip('/')
            })

        def main_js(request):
            config = self.get_config()
            return render(request, self.template_path("main.js"), {
                'configured': all(config.values()),
                'app_id': config['client_id'].split('-')[0],
                'user_id': request.user.id or '',
                **config
            }, content_type="text/javascript")

        return [
            MountPoint('$', settings_view),
            MountPoint('main.js$', main_js),
        ]

    def api_mount_points(self):
        return [
            MountPoint('projects/(?P<project_pk>[^/.]+)/tasks/(?P<pk>[^/.]+)/import$', ImportFiles.as_view()),
        ]
