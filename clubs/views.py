from django.conf import settings
from django.core.mail import send_mail
from rest_framework import serializers, viewsets, permissions

from .models import Club
from . import email

class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Object-level permission to only allow owners of an object to edit it.
    Assumes the model instance has an `owner` attribute.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Instance must have an attribute named `owner`.
        return obj.owner == request.user

class ClubSerializer(serializers.HyperlinkedModelSerializer):
    owner = serializers.SerializerMethodField()

    class Meta:
        model = Club
        fields = ('url', 'name', 'website', 'description', 'location',
                  'latitude', 'longitude', 'owner')

    def get_owner(self, obj):
        return obj.owner.username

class ClubViewSet(viewsets.ModelViewSet):
    """
    Clubs can be read by anyone, but creating a new club requires
    authentication. The user who created a club is its **owner** and
    they are the only one who can make future edits to it, aside
    from staff.
    """

    queryset = Club.objects.filter(is_active=True)
    serializer_class = ClubSerializer
    permission_classes = (permissions.IsAuthenticatedOrReadOnly,
                          IsOwnerOrReadOnly,)

    def perform_create(self, serializer):
        club = serializer.save(owner=self.request.user)
        send_mail(
            subject=email.CREATE_MAIL_SUBJECT,
            message=email.CREATE_MAIL_BODY % {
                'username': self.request.user.username
            },
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.request.user.email],
            # We don't want send failure to prevent a success response.
            fail_silently=True
        )
        if settings.TEACH_STAFF_EMAILS:
            send_mail(
                subject=email.CREATE_MAIL_STAFF_SUBJECT,
                message=email.CREATE_MAIL_STAFF_BODY % {
                    'username': self.request.user.username,
                    'email': self.request.user.email,
                    'club_name': club.name,
                    'club_location': club.location,
                    'club_website': club.website,
                    'club_description': club.description
                },
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=settings.TEACH_STAFF_EMAILS,
                # We don't want send failure to prevent a success response.
                fail_silently=True
            )

    def perform_destroy(self, serializer):
        instance = Club.objects.get(pk=serializer.pk)
        instance.is_active = False
        instance.save()
