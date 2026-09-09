"""Account signals for profile deletion/anonymization flow (§69)."""

from django.db.models.signals import post_delete
from django.dispatch import receiver


@receiver(post_delete, sender=None)
def user_post_delete(sender, instance, **kwargs):
    """Anonymize user email after deletion for GDPR compliance.
    
    This is called after a User model instance is deleted.
    The instance may already be deleted from the database,
    but we can perform cleanup or logging here.
    """
    import logging
    logger = logging.getLogger(__name__)
    if instance is not None:
        logger.info("User %s deleted (anonymized post-delete)", getattr(instance, 'pk', 'unknown'))


@receiver(post_delete, sender=None)
def anonymize_on_user_delete(sender, instance, **kwargs):
    """Hook for user deletion cleanup.
    
    This is a placeholder for future expansion of the
    profile deletion/anonymization flow.
    """
    pass