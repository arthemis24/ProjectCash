from django.conf.urls import patterns, url

from gateway.views import request_payment, set_momo_checkout, SetCheckout

urlpatterns = patterns(
    '',
    url(r'^request_payment/$', request_payment, name='request_payment'),
    url(r'^checkoutnow/(?P<token>[-\w]+)$', SetCheckout.as_view(), name='set_checkout'),
    url(r'^set_momo_checkout$', set_momo_checkout, name='set_momo_checkout'),
)
