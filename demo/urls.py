from django.conf.urls import patterns, url

from demo.views import DemoView, Print

urlpatterns = patterns(
    '',
    url(r'^$', DemoView.as_view(), name='home'),
    url(r'^print$', Print.as_view(), name='print'),
)
