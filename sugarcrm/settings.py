try:
    from django.conf import settings
except:
    settings = None

API_URL = getattr(settings, 'SUGAR_CRM_URL', '')
USERNAME = getattr(settings, 'SUGAR_CRM_USERNAME', '')
PASSWORD = getattr(settings, 'SUGAR_CRM_PASSWORD', '')
