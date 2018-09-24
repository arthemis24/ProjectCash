# -*- coding: utf-8 -*-
from ikwen.core.views import BaseView


class DemoView(BaseView):
    template_name = 'demo/home.html'


class Print(BaseView):
    template_name = 'demo/print.html'
