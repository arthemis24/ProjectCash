# -*- coding: utf-8 -*-
import json
import random
import string

import datetime
import traceback

import requests
from datetime import timedelta
from django.conf import settings
from django.core.urlresolvers import reverse
from django.http.response import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.module_loading import import_by_path
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from requests.exceptions import SSLError, Timeout, RequestException

from ikwen.core.utils import get_service_instance
from ikwen.core.models import Service
from ikwen.accesscontrol.models import Member
from ikwen.billing.models import MoMoTransaction
from ikwen.billing.orangemoney.views import ORANGE_MONEY, init_web_payment
from ikwen.billing.yup.views import init_yup_web_payment, YUP
from ikwen.billing.uba.views import init_uba_web_payment, UBA
from ikwen.billing.views import MoMoSetCheckout

from gateway.forms import PaymentRequestForm
from gateway.models import PaymentRequest, TERMINATED, PENDING

import logging
logger = logging.getLogger('ikwen')


def test_writing_on_log(request, *args, **kwargs):
    logger.debug("Writing test on info log")
    logger.error("Writing test on error log")
    response = HttpResponse(json.dumps(
        {
            'message': 'Done',
         }), 'content-type: text/json')
    return response


def generate_random_key(length):
    import random
    import string
    generated_key = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits)
                             for _ in range(length)])
    return generated_key


def generate_transaction_token():
    while True:
        key = generate_random_key(30)
        try:
            PaymentRequest.objects.get(token=key)
        except PaymentRequest.DoesNotExist:
            try:
                MoMoTransaction.objects.using('wallets').get(object_id=key)
            except MoMoTransaction.DoesNotExist:
                break
    return key


@csrf_exempt
def request_payment(request, *args, **kwargs):
    service = get_service_instance()
    logger.debug("%s - New query from %s: %s" % (service.project_name, request.META['REMOTE_ADDR'], request.META['REQUEST_URI']))

    form = PaymentRequestForm(request.GET)
    if form.is_valid():
        # TODO: Verifiy and send clear error messages. Use username instead of user_id
        username = request.GET.get('username')
        username = username.lower()
        amount = form.cleaned_data.get('amount')
        merchant_name = form.cleaned_data.get('merchant_name')
        notification_url = form.cleaned_data.get('notification_url')
        return_url = form.cleaned_data.get('return_url')
        cancel_url = form.cleaned_data.get('cancel_url')
        user_id = form.cleaned_data.get('user_id')
        try:
            amount = int(float(amount))
        except ValueError:
            response = {'errors': "Transaction amount must be a number, %s found." % amount}
            return HttpResponse(json.dumps(response))

        max_amount = getattr(settings, 'MAX_AMOUNT', 500000)
        if amount > max_amount:
            response = {'errors': "Amount too big. Max allowed is %d, %s found" % (max_amount, amount)}
            return HttpResponse(json.dumps(response))

        try:
            Service.objects.using('umbrella').get(project_name_slug=username)
        except Service.DoesNotExist:
            try:
                 Member.objects.using('umbrella').get(username=username)
            except Member.DoesNotExist:
                response = {'errors': "Username '%s' does not exist" % username}
                return HttpResponse(json.dumps(response))
        payment_request = PaymentRequest(user_id=user_id, ik_username=username, amount=amount,
                                         notification_url=notification_url, return_url=return_url,
                                         cancel_url=cancel_url, merchant_name=merchant_name)
        payment_request.token = generate_transaction_token()
        payment_request.save()
        logger.debug("%s - Token %s generated" % (service.project_name, payment_request.token))
        response = HttpResponse(json.dumps({
            'success': True,
            'token': payment_request.token
        }), 'content-type: text/json')
    else:
        error_list = []
        for error in form.errors:
            error_list.append(error)
        response = HttpResponse(json.dumps({
            'message': 'One or more parameters not found in your request',
            'errors': error_list,
        }), 'content-type: text/json')
    return response


class SetCheckout(MoMoSetCheckout):

    @method_decorator(never_cache)
    def get(self, request, *args, **kwargs):
        context = self.get_context_data(**kwargs)
        token = kwargs['token']
        payment_request = get_object_or_404(PaymentRequest, token=token)
        token_timeout = getattr(settings, 'TOKEN_TIMEOUT', 5) * 60
        token_expiry = payment_request.created_on + timedelta(seconds=token_timeout)
        now = datetime.datetime.now()
        if not getattr(settings, 'DEBUG', False):
            if now > token_expiry:
                # Token is expired
                return HttpResponse(json.dumps({'error': "expired token; restart your request"}), 'content-type: text/json')
        payment_mean = context['payment_mean']
        payment_request.mean = payment_mean.slug
        payment_request.save()
        signature = ''.join([random.SystemRandom().choice(string.ascii_letters + string.digits) for i in range(16)])
        request.session['signature'] = signature
        path = getattr(settings, 'MOMO_BEFORE_CASH_OUT')
        momo_before_checkout = import_by_path(path)
        http_resp = momo_before_checkout(request, payment_mean, *args, **kwargs)

        if http_resp:
            return http_resp
        if payment_mean.slug == ORANGE_MONEY:
            return init_web_payment(request, *args, **kwargs)
        if payment_mean.slug == YUP:
            return init_yup_web_payment(request, *args, **kwargs)
        if payment_mean.slug == UBA:
            return init_uba_web_payment(request, *args, **kwargs)
        context['amount'] = request.session['amount']
        return render(request, self.template_name, context)


def set_momo_checkout(request, *args, **kwargs):
    token = kwargs['token']

    try:
        payment_request = PaymentRequest.objects.get(token=token, status=PENDING)
    except PaymentRequest.DoesNotExist:
        return HttpResponse("Error, PaymentRequest does not exist.")
    else:
        request.session['model_name'] = 'gateway.PaymentRequest'
        request.session['object_id'] = payment_request.token
        request.session['amount'] = payment_request.amount

        request.session['merchant_name'] = payment_request.merchant_name
        request.session['notif_url'] = get_service_instance().url + reverse('gateway:do_momo_checkout')
        request.session['cancel_url'] = payment_request.cancel_url
        request.session['return_url'] = payment_request.return_url

    if request.GET.get('mean') == UBA:
        request.session['description'] = 'Payment Request'
        request.session['noOfItems'] = 1


def after_cashout(request, *args, **kwargs):
    tx = kwargs.get('transaction')
    svc = get_service_instance()
    try:
        token = request.session['object_id']
    except KeyError:
        token = tx.object_id
    try:
        payment_request = PaymentRequest.objects.get(token=token)
    except PaymentRequest.DoesNotExist:
        logger.debug("%s - The payment request %s was not found" % (svc.project_name, token), exc_info=True)
    else:
        try:
            transaction = MoMoTransaction.objects.using('wallets').get(object_id=token)
        except MoMoTransaction.DoesNotExist:
            logger.error("%s - MoMo Transaction with object_id: %s was not found" % (svc.project_name, token), exc_info=True)
            return
        except MoMoTransaction.MultipleObjectsReturned:
            transaction = MoMoTransaction.objects.using('wallets').filter(object_id=token)[0]
            logger.error("%s - Multiple MoMoTransation found with object_id %s was not found" % (svc.project_name, token), exc_info=True)

        phone = transaction.phone
        token = payment_request.token
        amount = payment_request.amount
        transaction.username = payment_request.user_id
        try:
            transaction.service_id = Service.objects.using('umbrella').get(project_name_slug=payment_request.ik_username).id
        except:
            pass

        r = None
        try:
            payment_request.momo_transaction_id = transaction.id
            payment_request.status = TERMINATED
            payment_request.save()
            logger.debug("%s - Request of %dF from %s with token %s Terminated" % (svc.project_name, amount, phone, token))
            params = {
                "status": transaction.status,
                "message": transaction.message,
                "operator_tx_id": transaction.processor_tx_id,
                "phone": transaction.phone
            }
            r = requests.get(payment_request.notification_url, params=params)
        except SSLError:
            logger.error("SSL Error", exc_info=True)
            payment_request.notification_resp_code = r.status_code if r else None
            payment_request.message = traceback.format_exc()
        except Timeout:
            logger.error("Time out", exc_info=True)
            payment_request.notification_resp_code = r.status_code if r else None
            payment_request.message = traceback.format_exc()
        except RequestException:
            logger.error("Request exception", exc_info=True)
            payment_request.notification_resp_code = r.status_code if r else None
            payment_request.message = traceback.format_exc()
        except:
            logger.error("Server error", exc_info=True)
            payment_request.notification_resp_code = r.status_code if r else None
            payment_request.message = traceback.format_exc()
        else:
            logger.debug("%s - Notification for %dF from %s successfully sent using URL %s" % (svc.project_name, amount, token, r.url))

        payment_request.save()
        transaction.save()


def do_momo_checkout(request, *args, **kwargs):
    url = get_service_instance().url + reverse('gateway:do_momo_checkout', args=('1000', ))
    return HttpResponse("Not yet implemented" + url)
