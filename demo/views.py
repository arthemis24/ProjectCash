# -*- coding: utf-8 -*-

from django.views.generic import TemplateView


class DemoView(TemplateView):
    template_name = 'demo/home.html'


class Print(TemplateView):
    template_name = 'demo/print.html'
