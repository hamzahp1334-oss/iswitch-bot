import logging
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_USER_IDS
from database.crud import is_admin, update_admin_last_seen
from services.audit import log_admin_action

logger = logging.getLogger("iswitch.admin.auth")

async def verify_admin_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False

    is_authorized = await is_admin(user.id)
    if not is_authorized:
        logger.warning(f"UNAUTHORIZED ADMIN ACCESS ATTEMPT: User ID {user.id} (@{user.username}, {user.full_name})")
        await log_admin_action(
            admin_id=user.id,
            action="unauthorized_access_denied",
            target_type="admin_bot",
            target_id=str(user.id),
            details=f"Username: @{user.username}, Name: {user.full_name}"
        )

        msg = (
            "⛔ *Access Denied*\n\n"
            "You are not authorized to access the iSwitch Administration System.\n"
            "This incident has been logged for security purposes."
        )
        from services.ui_utils import safe_edit_or_send
        await safe_edit_or_send(update, context, text=msg)
        return False

    # Update last seen
    await update_admin_last_seen(user.id, username=user.username, first_name=user.first_name)
    return True
