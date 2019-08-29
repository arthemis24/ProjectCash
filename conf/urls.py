from django.conf.urls import patterns, include, url

from django.contrib import admin

from demo.views import DemoView
from gateway.views import test_writing_on_log
from ikwen.accesscontrol.views import SignInMinimal

admin.autodiscover()

urlpatterns = patterns(
    '',
    url(r'^admin/', include(admin.site.urls)),
    url(r'^v1/', include('gateway.urls', namespace='gateway')),
    url(r'^demo/', include('demo.urls', namespace='demo')),
    url(r'^ikwen/', include('ikwen.core.urls', namespace='ikwen')),
    url(r'^billing/', include('ikwen.billing.urls', namespace='billing')),
    url(r'^$', SignInMinimal.as_view(), name='sign_in'),
    url(r'^$', DemoView.as_view(), name='home'),
    url(r'^test_writing_on_log', test_writing_on_log, name='test_writing_on_log'),
)
