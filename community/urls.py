from rest_framework.routers import DefaultRouter

from .views import MyEmergencyContactsViewSet, MyGuardiansViewSet, SocietyViewSet

router = DefaultRouter()
router.register("societies", SocietyViewSet, basename="society")
router.register("my/guardians", MyGuardiansViewSet, basename="my-guardians")
router.register("my/emergency-contacts", MyEmergencyContactsViewSet,
                basename="my-emergency-contacts")

urlpatterns = router.urls
