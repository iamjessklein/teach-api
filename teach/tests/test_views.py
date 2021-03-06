import json
from django.test import TestCase, RequestFactory, Client
from django.test.utils import override_settings
from django.contrib.auth.models import User
from django_browserid.base import MockVerifier, VerificationResult

from .. import views
from .. import webmaker

class FakeBrowserIDBackend(webmaker.WebmakerBrowserIDBackend):
    def __init__(self, email):
        super(FakeBrowserIDBackend, self).__init__()
        self.__fake_email = email

    def get_verifier(self):
        return MockVerifier(self.__fake_email)

class ViewSmokeTests(TestCase):
    def setUp(self):
        self.client = Client()

    def login(self):
        User.objects.create_user('foo', 'foo@example.org', 'pass')
        self.assertTrue(self.client.login(username='foo',
                                          password='pass'))

    def verify_200(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_api_root(self):
        self.verify_200('/api/')

    def test_api_introduction(self):
        self.verify_200('/api-introduction/')

    def test_authenticated_api_introduction(self):
        self.login()
        self.verify_200('/api-introduction/')

class CorsTests(TestCase):
    def test_api_paths_have_cors_enabled(self):
        c = Client()
        response = c.get('/api/', HTTP_ORIGIN='http://foo.org')
        self.assertEqual(response['access-control-allow-origin'], '*')

    def test_non_api_paths_have_cors_disabled(self):
        c = Client()
        response = c.get('/admin/', HTTP_ORIGIN='http://foo.org')
        self.assertFalse('access-control-allow-origin' in response)

@override_settings(CORS_API_PERSONA_ORIGINS=['http://example.org'],
                   DEBUG=False)
class PersonaTokenToAPITokenTests(TestCase):
    def setUp(self):
        self.view = views.persona_assertion_to_api_token
        self.factory = RequestFactory()

    def test_403_when_origin_is_absent(self):
        req = self.factory.post('/')
        response = self.view(req)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content, 'invalid origin')

    def test_403_when_origin_is_not_whitelisted(self):
        req = self.factory.post('/', HTTP_ORIGIN='http://foo.com')
        response = self.view(req)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content, 'invalid origin')

    @override_settings(CORS_API_PERSONA_ORIGINS=['*'], DEBUG=True)
    def test_any_origin_allowed_when_debugging(self):
        req = self.factory.post('/', HTTP_ORIGIN='http://foo.com')
        response = self.view(req)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, 'assertion required')

    @override_settings(CORS_API_PERSONA_ORIGINS=['*'], DEBUG=False)
    def test_any_origin_not_allowed_when_not_debugging(self):
        req = self.factory.post('/', HTTP_ORIGIN='http://foo.com')
        response = self.view(req)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content, 'invalid origin')

    def test_cors_header_is_valid(self):
        req = self.factory.post('/', HTTP_ORIGIN='http://example.org')
        response = self.view(req)
        self.assertEqual(response['access-control-allow-origin'],
                         'http://example.org')

    def test_400_when_assertion_not_present(self):
        req = self.factory.post('/', HTTP_ORIGIN='http://example.org')
        response = self.view(req)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, 'assertion required')

    def request_with_assertion(self, email):
        req = self.factory.post('/', {
            'assertion': 'foo'
        }, HTTP_ORIGIN='http://example.org')
        response = self.view(req, backend=FakeBrowserIDBackend(email))
        self.assertEqual(response['access-control-allow-origin'],
                         'http://example.org')
        if response['Content-Type'] == 'application/json':
            response.json = json.loads(response.content)
        return response

    def test_403_when_assertion_invalid(self):
        response = self.request_with_assertion(email=None)
        self.assertEqual(response.content, 'invalid assertion or email')

    def test_200_when_assertion_valid_and_account_exists(self):
        User.objects.create_user('foo', 'foo@example.org')
        response = self.request_with_assertion(email='foo@example.org')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['username'], 'foo')
        self.assertRegexpMatches(response.json['token'], r'^[0-9a-f]+$')
