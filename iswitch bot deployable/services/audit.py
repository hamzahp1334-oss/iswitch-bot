import logging
from database.crud import log_audit_action

logger = logging.getLogger("iswitch.audit")

async def log_admin_action(
    admin_id: int,
    action: str,
    target_type: str,
    target_id: str | int,
    previous_value: str = None,
    new_value: str = None,
    details: str = None
):
    try:
        await log_audit_action(
            admin_id=admin_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            prev_val=previous_value,
            new_val=new_value,
            details=details
        )
        logger.info(f"Audit: Admin {admin_id} did {action} on {target_type} #{target_id}")
    except Exception as e:
        logger.error(f"Failed to record audit log: {e}")
