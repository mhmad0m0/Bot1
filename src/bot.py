# Telegram Bot configuration and handlers
import os
import logging
import sys # Added sys for path manipulation
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)

# --- App Context for Database Operations ---
# This section needs to be careful with imports when running bot standalone vs with Flask app
# For Render.com, bot and web will be separate processes but can share the same DB.

project_root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if project_root_path not in sys.path:
    sys.path.insert(0, project_root_path)

# Try to import Flask app and db for context, but make it optional if bot runs standalone
try:
    from src.main import app as flask_app, db
    from src.models.mod import Mod
    from src.models.category import Category
    from src.models.admin import Admin
    FLASK_APP_AVAILABLE = True
except ImportError as e:
    FLASK_APP_AVAILABLE = False
    logging.warning(f"Flask app context not available for bot (may be running standalone): {e}")
    # Define dummy db and models if Flask app is not available to prevent crashes on import
    # This is a simplified approach; a more robust solution might involve a shared DB session manager
    class DummyDB:
        def __init__(self):
            self.session = None # Or a mock session
    db = DummyDB()
    Mod = Category = Admin = None 

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Configuration ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("FATAL: TELEGRAM_BOT_TOKEN environment variable not set.")
    sys.exit("TELEGRAM_BOT_TOKEN not set.")

OWNER_TELEGRAM_ID = 7839645457 # This could also be an environment variable if it changes
UPLOAD_FOLDER = os.path.join(project_root_path, "src", "static", "uploads", "mods_images")
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True) # Added exist_ok=True

# --- Conversation Handler States ---
(ADD_MOD_NAME, ADD_MOD_DESCRIPTION, ADD_MOD_LINK, ADD_MOD_IMAGE, ADD_MOD_CONFIRM,
 CAT_MANAGE_MENU, ADD_CAT_GET_NAME, ADD_CAT_CONFIRM,
 LIST_CATS_EDIT, EDIT_CAT_GET_NEW_NAME, EDIT_CAT_CONFIRM,
 LIST_CATS_DELETE, DELETE_CAT_CONFIRM,
 SUGGEST_MOD_NAME, SUGGEST_MOD_DESCRIPTION, SUGGEST_MOD_LINK, SUGGEST_MOD_IMAGE, SUGGEST_MOD_CONFIRM,
 REVIEW_SUGGESTED_MODS_LIST, REVIEW_MOD_ACTION 
 ) = range(20)

# --- Helper Functions ---
def is_owner(update: Update) -> bool:
    return update.effective_user.id == OWNER_TELEGRAM_ID

# Decorator to ensure Flask app context for database operations
def with_flask_context(func):
    async def wrapper(*args, **kwargs):
        if FLASK_APP_AVAILABLE and flask_app:
            with flask_app.app_context():
                return await func(*args, **kwargs)
        else:
            logger.warning(f"Flask app context not available for {func.__name__}. DB operations might fail.")
            # Proceed without context if Flask app is not available (e.g. running bot standalone for testing without DB)
            # Or, handle this case more gracefully, e.g., by returning an error message to the user.
            # For now, we let it proceed, but DB calls will likely fail.
            return await func(*args, **kwargs)
    return wrapper

@with_flask_context
async def go_to_main_menu_owner(update: Update, context: ContextTypes.DEFAULT_TYPE, query_to_edit=None):
    user = update.effective_user
    pending_mods_count = 0
    if Mod: # Check if Mod model is available
        pending_mods_count = Mod.query.filter_by(status=\"pending_approval\").count()

    keyboard = [
        [InlineKeyboardButton("➕ إضافة مود جديد", callback_data=\"add_mod_start\"),
         InlineKeyboardButton("🗂️ إدارة الأقسام", callback_data=\"manage_categories_menu\ically
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = f"أهلاً بك يا مالك البوت! {user.first_name}\nاختر الإجراء المطلوب:"
    
    active_query = query_to_edit or (update.callback_query if hasattr(update, \"callback_query\") and update.callback_query else None)

    if active_query:
        try:
            await active_query.edit_message_text(text=message_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message for main menu: {e}")
            if hasattr(update, \"effective_chat\") and update.effective_chat:
                 await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup)
            else: 
                 logger.warning("Could not send main menu as new message after edit failed.")
    elif hasattr(update, \"message\") and update.message:
        await update.message.reply_text(text=message_text, reply_markup=reply_markup)

# --- Command Handlers ---
@with_flask_context
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if is_owner(update):
        if Admin and db: # Check if Admin model and db are available
            owner_db = Admin.query.filter_by(telegram_id=OWNER_TELEGRAM_ID).first()
            if not owner_db:
                new_owner = Admin(telegram_id=OWNER_TELEGRAM_ID, role=\"owner\", username=user.username or str(OWNER_TELEGRAM_ID))
                db.session.add(new_owner)
                db.session.commit()
        await go_to_main_menu_owner(update, context)
    else:
        keyboard = [[InlineKeyboardButton("💡 اقتراح مود جديد", callback_data=\"suggest_new_mod_start\")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"أهلاً بك {user.first_name} في بوت نشر المودات!\nيمكنك اقتراح مود جديد ليتم إضافته إلى الموقع.",
            reply_markup=reply_markup
        )
    return ConversationHandler.END

# --- Generic Mod Input Functions (for Owner Add & User Suggest) ---
async def _get_mod_name(update: Update, context: ContextTypes.DEFAULT_TYPE, for_suggestion: bool) -> int:
    state_key = "suggested_mod" if for_suggestion else "current_mod"
    context.user_data[state_key]["name"] = update.message.text
    await update.message.reply_text("تم حفظ الاسم. يرجى إرسال **وصف المود**:", parse_mode=\"Markdown\")
    return SUGGEST_MOD_DESCRIPTION if for_suggestion else ADD_MOD_DESCRIPTION

async def _get_mod_description(update: Update, context: ContextTypes.DEFAULT_TYPE, for_suggestion: bool) -> int:
    state_key = "suggested_mod" if for_suggestion else "current_mod"
    context.user_data[state_key]["description"] = update.message.text
    await update.message.reply_text("تم حفظ الوصف. يرجى إرسال **رابط تحميل المود**:", parse_mode=\"Markdown\")
    return SUGGEST_MOD_LINK if for_suggestion else ADD_MOD_LINK

async def _get_mod_link(update: Update, context: ContextTypes.DEFAULT_TYPE, for_suggestion: bool) -> int:
    state_key = "suggested_mod" if for_suggestion else "current_mod"
    context.user_data[state_key]["download_link"] = update.message.text
    await update.message.reply_text("تم حفظ الرابط. يرجى إرسال **صورة للمود**:", parse_mode=\"Markdown\")
    return SUGGEST_MOD_IMAGE if for_suggestion else ADD_MOD_IMAGE

async def _get_mod_image(update: Update, context: ContextTypes.DEFAULT_TYPE, for_suggestion: bool) -> int:
    state_key = "suggested_mod" if for_suggestion else "current_mod"
    photo_file = await update.message.photo[-1].get_file()
    file_extension = os.path.splitext(photo_file.file_path)[1] if photo_file.file_path else ".jpg"
    image_filename = f"mod_{update.message.message_id}_{photo_file.file_unique_id}{file_extension}"
    image_path = os.path.join(UPLOAD_FOLDER, image_filename)
    await photo_file.download_to_drive(image_path)
    context.user_data[state_key]["image_filename"] = image_filename
    mod_info = context.user_data[state_key]
    action_text = "اقتراح" if for_suggestion else "إضافة"
    confirm_callback_yes = \"confirm_suggest_mod_yes\" if for_suggestion else \"confirm_add_mod_yes\"
    confirm_callback_cancel = \"confirm_suggest_mod_cancel\" if for_suggestion else \"confirm_add_mod_cancel\"
    text = (f"**تفاصيل المود ال{action_text}:**\n"
            f"الاسم: {mod_info[\"name\"]}\n"
            f"الوصف: {mod_info[\"description\"]}\n"
            f"الرابط: {mod_info[\"download_link\"]}\n"
            f"الصورة: {mod_info[\"image_filename\"]} (تم الحفظ)\n\n"
            f"هل تريد تأكيد {action_text} هذا المود؟")
    keyboard = [
        [InlineKeyboardButton(f"✅ نعم، {action_text}", callback_data=confirm_callback_yes)],
        [InlineKeyboardButton(f"❌ لا، إلغاء", callback_data=confirm_callback_cancel)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=\"Markdown\")
    return SUGGEST_MOD_CONFIRM if for_suggestion else ADD_MOD_CONFIRM

# --- Add Mod Conversation (Owner) ---
@with_flask_context
async def add_mod_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_owner(update):
        await query.edit_message_text(text="عذراً، هذا الإجراء مخصص للمالك فقط.")
        return ConversationHandler.END
    context.user_data["current_mod"] = {}
    await query.edit_message_text(text="يرجى إرسال **اسم المود**:", parse_mode=\"Markdown\")
    return ADD_MOD_NAME

async def get_owner_mod_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_name(update, context, False)
async def get_owner_mod_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_description(update, context, False)
async def get_owner_mod_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_link(update, context, False)
async def get_owner_mod_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_image(update, context, False)

@with_flask_context
async def confirm_add_mod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == \"confirm_add_mod_yes\":
        mod_data = context.user_data["current_mod"]
        if not Mod or not db: # Check if Mod and db are available
            await query.edit_message_text(text="خطأ في الاتصال بقاعدة البيانات.")
            return ConversationHandler.END
        try:
            new_mod = Mod(
                name=mod_data[\"name\"], description=mod_data[\"description\"],
                download_link=mod_data[\"download_link\"], image_filename=mod_data[\"image_filename\"],
                uploader_telegram_id=OWNER_TELEGRAM_ID, status=\"approved\"
            )
            db.session.add(new_mod)
            db.session.commit()
            await query.edit_message_text(text=f"✅ تم إضافة المود \"{mod_data[\"name\"]}\" بنجاح!")
        except Exception as e:
            logger.error(f"Error adding mod to DB: {e}")
            await query.edit_message_text(text="حدث خطأ أثناء إضافة المود إلى قاعدة البيانات.")
    else:
        await query.edit_message_text(text="تم إلغاء عملية إضافة المود.")
    context.user_data.pop("current_mod", None)
    await go_to_main_menu_owner(update, context, query_to_edit=query)
    return ConversationHandler.END

# --- Suggest Mod Conversation (User) ---
async def suggest_new_mod_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["suggested_mod"] = {}
    await query.edit_message_text(text="لإقتراح مود، يرجى إرسال **اسم المود**:", parse_mode=\"Markdown\")
    return SUGGEST_MOD_NAME

async def get_user_mod_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_name(update, context, True)
async def get_user_mod_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_description(update, context, True)
async def get_user_mod_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_link(update, context, True)
async def get_user_mod_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: return await _get_mod_image(update, context, True)

@with_flask_context
async def confirm_suggest_mod_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user = update.effective_user
    await query.answer()
    if query.data == \"confirm_suggest_mod_yes\":
        mod_data = context.user_data["suggested_mod"]
        if not Mod or not db: # Check if Mod and db are available
            await query.edit_message_text(text="خطأ في الاتصال بقاعدة البيانات.")
            return ConversationHandler.END
        try:
            new_mod_suggestion = Mod(
                name=mod_data[\"name\"], description=mod_data[\"description\"],
                download_link=mod_data[\"download_link\"], image_filename=mod_data[\"image_filename\"],
                uploader_telegram_id=user.id, status=\"pending_approval\"
            )
            db.session.add(new_mod_suggestion)
            db.session.commit()
            await query.edit_message_text(text=f"✅ شكراً لك! تم استلام اقتراحك للمود \"{mod_data[\"name\"]}\" وسيتم مراجعته.")
            owner_message = (f"🔔 اقتراح مود جديد من المستخدم {user.first_name} (ID: {user.id}):\n"
                             f"الاسم: {mod_data[\"name\"]}\nالوصف: {mod_data[\"description\"]}\n"
                             f"الرابط: {mod_data[\"download_link\"]}\nالصورة: {mod_data[\"image_filename\"]}")
            await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=owner_message)
        except Exception as e:
            logger.error(f"Error saving mod suggestion to DB: {e}")
            await query.edit_message_text(text="حدث خطأ أثناء حفظ اقتراحك.")
    else:
        await query.edit_message_text(text="تم إلغاء عملية اقتراح المود.")
    context.user_data.pop("suggested_mod", None)
    return ConversationHandler.END

# --- Review Suggested Mods (Owner) ---
@with_flask_context
async def review_suggested_mods_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_owner(update):
        await query.edit_message_text(text="عذراً، هذا الإجراء مخصص للمالك فقط.")
        return ConversationHandler.END

    if not Mod: # Check if Mod model is available
        await query.edit_message_text(text="خطأ: نموذج المودات غير متوفر.")
        return ConversationHandler.END
        
    pending_mods = Mod.query.filter_by(status=\"pending_approval\").order_by(Mod.created_at.asc()).all()
    
    if not pending_mods:
        await query.edit_message_text(text="لا توجد مودات مقترحة للمراجعة حالياً.")
        await go_to_main_menu_owner(update, context, query_to_edit=query)
        return ConversationHandler.END

    context.user_data[\"pending_mods_list\"] = [mod.id for mod in pending_mods]
    context.user_data[\"current_review_index\"] = 0
    
    return await display_pending_mod_for_review(update, context, query_to_edit=query)

@with_flask_context
async def display_pending_mod_for_review(update: Update, context: ContextTypes.DEFAULT_TYPE, query_to_edit=None) -> int:
    idx = context.user_data.get(\"current_review_index\", 0)
    pending_ids = context.user_data.get(\"pending_mods_list\", [])

    if idx >= len(pending_ids):
        message_text = "لا توجد مودات مقترحة أخرى للمراجعة."
        active_query_for_edit = query_to_edit or (update.callback_query if hasattr(update, \"callback_query\") and update.callback_query else None)
        if active_query_for_edit:
            await active_query_for_edit.edit_message_text(text=message_text)
        # else: # If no query, maybe send a new message or log
        #    await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text)
        await go_to_main_menu_owner(update, context, query_to_edit=active_query_for_edit)
        return ConversationHandler.END

    mod_id = pending_ids[idx]
    if not Mod: # Check if Mod model is available
        # Handle error appropriately, maybe edit message or send new one
        return ConversationHandler.END
        
    mod_to_review = Mod.query.get(mod_id)

    if not mod_to_review:
        error_message = "خطأ: لم يتم العثور على المود المقترح."
        active_query_for_edit = query_to_edit or (update.callback_query if hasattr(update, \"callback_query\") and update.callback_query else None)
        if active_query_for_edit:
            await active_query_for_edit.edit_message_text(text=error_message)
        await go_to_main_menu_owner(update, context, query_to_edit=active_query_for_edit)
        return ConversationHandler.END

    context.user_data[\"current_review_mod_id\"] = mod_id
    uploader_info = f" (المقترح: {mod_to_review.uploader_telegram_id})"
    text = (f"**مراجعة مود مقترح ({idx + 1}/{len(pending_ids)}):**{uploader_info}\n"
            f"الاسم: {mod_to_review.name}\n"
            f"الوصف: {mod_to_review.description}\n"
            f"الرابط: {mod_to_review.download_link}\n"
            f"الصورة: {mod_to_review.image_filename}")
    
    keyboard = [
        [InlineKeyboardButton("✅ موافقة ونشر", callback_data=f\"review_action_approve_{mod_id}\")],
        [InlineKeyboardButton("❌ رفض الاقتراح", callback_data=f\"review_action_reject_{mod_id}\")],
        [InlineKeyboardButton("⏭️ تخطي (للمراجعة لاحقاً)", callback_data=\"review_action_skip\")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data=\"main_menu_from_review\")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    active_query = query_to_edit or (update.callback_query if hasattr(update, \"callback_query\") and update.callback_query else None)
    # When editing, we can't send a new photo. We should send the photo first, then the text with buttons.
    # This part needs rethinking for a better UX if image is present.
    # For now, just sending text.
    if active_query:
        await active_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=\"Markdown\")
    elif hasattr(update, \"effective_chat\") and update.effective_chat:
        # This case might not be hit often if we always come from a callback query
        if mod_to_review.image_filename:
            image_full_path = os.path.join(UPLOAD_FOLDER, mod_to_review.image_filename)
            if os.path.exists(image_full_path):
                try:
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=open(image_full_path, \"rb\"))
                except Exception as e:
                    logger.error(f"Error sending photo for review: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode=\"Markdown\")

    return REVIEW_MOD_ACTION

@with_flask_context
async def review_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    action_data = query.data

    if not Mod or not db: # Check if Mod and db are available
        await query.edit_message_text(text="خطأ في الاتصال بقاعدة البيانات.")
        return ConversationHandler.END

    if action_data == \"review_action_skip\":
        context.user_data[\"current_review_index\"] = context.user_data.get(\"current_review_index\", 0) + 1
        return await display_pending_mod_for_review(update, context, query_to_edit=query)
    elif action_data == \"main_menu_from_review\":
        await go_to_main_menu_owner(update, context, query_to_edit=query)
        return ConversationHandler.END

    try:
        action_type, mod_id_str = action_data.split(\"_\")[-2:]
        mod_id = int(mod_id_str)
        mod_to_update = Mod.query.get(mod_id)

        if not mod_to_update:
            await query.edit_message_text("خطأ: لم يتم العثور على المود لتحديث حالته.")
            return ConversationHandler.END # Or go to main menu

        if action_type == \"approve\":
            mod_to_update.status = \"approved\"
            db.session.commit()
            await query.edit_message_text(f"✅ تم الموافقة على المود \"{mod_to_update.name}\" ونشره.")
            # Optionally notify the suggester
            if mod_to_update.uploader_telegram_id != OWNER_TELEGRAM_ID:
                try:
                    await context.bot.send_message(chat_id=mod_to_update.uploader_telegram_id, text=f"🎉 تهانينا! تم الموافقة على اقتراحك للمود \"{mod_to_update.name}\" ونشره على الموقع.")
                except Exception as e:
                    logger.warning(f"Could not notify suggester {mod_to_update.uploader_telegram_id}: {e}")
        elif action_type == \"reject\":
            mod_to_update.status = \"rejected\" # Or delete it, or keep for record
            db.session.commit()
            await query.edit_message_text(f"❌ تم رفض المود \"{mod_to_update.name}\".")
            # Optionally notify the suggester
            if mod_to_update.uploader_telegram_id != OWNER_TELEGRAM_ID:
                try:
                    await context.bot.send_message(chat_id=mod_to_update.uploader_telegram_id, text=f"😕 نأسف لإبلاغك بأنه تم رفض اقتراحك للمود \"{mod_to_update.name}\" حالياً.")
                except Exception as e:
                    logger.warning(f"Could not notify suggester {mod_to_update.uploader_telegram_id}: {e}")
        else:
            await query.edit_message_text("إجراء غير معروف.")
            return ConversationHandler.END

    except ValueError:
        await query.edit_message_text("خطأ في بيانات الإجراء.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error processing review action: {e}")
        await query.edit_message_text("حدث خطأ أثناء معالجة الإجراء.")
        return ConversationHandler.END

    # Move to the next mod or end review
    context.user_data[\"current_review_index\"] = context.user_data.get(\"current_review_index\", 0) + 1
    return await display_pending_mod_for_review(update, context, query_to_edit=query)

# --- Category Management (Owner) ---
@with_flask_context
async def manage_categories_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if not is_owner(update):
        await query.edit_message_text(text="عذراً، هذا الإجراء مخصص للمالك فقط.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ إضافة قسم جديد", callback_data=\"add_category_start\")],
        # [InlineKeyboardButton("✏️ تعديل قسم موجود", callback_data=\"edit_category_list\")], # TODO
        # [InlineKeyboardButton("🗑️ حذف قسم موجود", callback_data=\"delete_category_list\")], # TODO
        [InlineKeyboardButton("📋 عرض كل الأقسام", callback_data=\"list_all_categories\")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data=\"main_menu_from_cat_manage\")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text="إدارة الأقسام:", reply_markup=reply_markup)
    return CAT_MANAGE_MENU

@with_flask_context
async def list_all_categories_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not Category:
        await query.edit_message_text("خطأ: نموذج الأقسام غير متوفر.")
        return CAT_MANAGE_MENU
        
    categories = Category.query.order_by(Category.name).all()
    if not categories:
        text = "لا توجد أقسام مضافة حالياً."
    else:
        text = "**الأقسام الحالية:**\n" + "\n".join([f"- {cat.name} (ID: {cat.id})" for cat in categories])
    
    # Re-show category management menu after listing
    keyboard = [
        [InlineKeyboardButton("➕ إضافة قسم جديد", callback_data=\"add_category_start\")],
        [InlineKeyboardButton("🔙 العودة لقائمة إدارة الأقسام", callback_data=\"manage_categories_menu_from_list\")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=\"Markdown\")
    return CAT_MANAGE_MENU # Stay in category management menu

async def add_category_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["new_category"] = {}
    await query.edit_message_text(text="يرجى إرسال **اسم القسم الجديد** الذي تريد إضافته:", parse_mode=\"Markdown\")
    return ADD_CAT_GET_NAME

async def get_new_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_category"]["name"] = update.message.text
    cat_name = context.user_data["new_category"]["name"]
    keyboard = [
        [InlineKeyboardButton("✅ نعم، إضافة", callback_data=\"confirm_add_category_yes\")],
        [InlineKeyboardButton("❌ لا، إلغاء", callback_data=\"confirm_add_category_cancel\")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"هل أنت متأكد أنك تريد إضافة قسم باسم \"{cat_name}\"؟", reply_markup=reply_markup)
    return ADD_CAT_CONFIRM

@with_flask_context
async def confirm_add_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == \"confirm_add_category_yes\":
        cat_name = context.user_data["new_category"]["name"]
        if not Category or not db: # Check if Category and db are available
            await query.edit_message_text(text="خطأ في الاتصال بقاعدة البيانات.")
            return CAT_MANAGE_MENU
        try:
            # Check if category already exists (case-insensitive check might be better)
            existing_category = Category.query.filter(Category.name.ilike(cat_name)).first()
            if existing_category:
                await query.edit_message_text(f"⚠️ القسم \"{cat_name}\" موجود بالفعل.")
            else:
                new_cat = Category(name=cat_name)
                db.session.add(new_cat)
                db.session.commit()
                await query.edit_message_text(f"✅ تم إضافة القسم \"{cat_name}\" بنجاح!")
        except Exception as e:
            logger.error(f"Error adding category to DB: {e}")
            await query.edit_message_text("حدث خطأ أثناء إضافة القسم إلى قاعدة البيانات.")
    else:
        await query.edit_message_text("تم إلغاء عملية إضافة القسم.")
    context.user_data.pop("new_category", None)
    # Go back to category management menu
    await manage_categories_menu_callback(update, context) # This might need query_to_edit if called directly
    return CAT_MANAGE_MENU

# --- View Stats (Owner) ---
@with_flask_context
async def view_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_owner(update):
        await query.edit_message_text(text="عذراً، هذا الإجراء مخصص للمالك فقط.")
        return ConversationHandler.END # Or just return if not in a conversation

    if not Mod: # Check if Mod model is available
        await query.edit_message_text(text="خطأ: نموذج المودات غير متوفر.")
        return # Or go to main menu

    total_mods = Mod.query.count()
    approved_mods = Mod.query.filter_by(status=\"approved\").count()
    pending_mods = Mod.query.filter_by(status=\"pending_approval\").count()
    rejected_mods = Mod.query.filter_by(status=\"rejected\").count()
    # total_views = db.session.query(db.func.sum(Mod.view_count)).scalar() or 0
    # total_downloads = db.session.query(db.func.sum(Mod.download_count)).scalar() or 0

    stats_text = (f"📊 **إحصائيات الموقع:**\n"
                  f"▫️ إجمالي المودات (كل الحالات): {total_mods}\n"
                  f" одобрен إجمالي المودات المنشورة: {approved_mods}\n"
                  f"⏳ إجمالي المودات قيد المراجعة: {pending_mods}\n"
                  f"❌ إجمالي المودات المرفوضة: {rejected_mods}\n"
                  # f"👁️ إجمالي المشاهدات: {total_views}\n"
                  # f"📥 إجمالي التنزيلات: {total_downloads}"
                  )
    await query.edit_message_text(text=stats_text, parse_mode=\"Markdown\")
    await go_to_main_menu_owner(update, context, query_to_edit=query)
    # Not in a conversation, so no state to return or ConversationHandler.END

# --- Fallback and Error Handlers ---
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("عذراً، لم أفهم هذا الأمر. استخدم /start لبدء التفاعل.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    # Optionally, notify the user or owner about the error
    if update and hasattr(update, \"effective_message\") and update.effective_message:
        try:
            await update.effective_message.reply_text("حدث خطأ ما أثناء معالجة طلبك. تم إبلاغ المطور.")
        except Exception as e:
            logger.error(f"Error sending error message to user: {e}")

# --- Main Bot Setup ---
def main() -> None:
    if not BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is not set in environment variables.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for adding a mod (owner)
    add_mod_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_mod_start_callback, pattern=\"^add_mod_start$\")],
        states={
            ADD_MOD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_owner_mod_name)],
            ADD_MOD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_owner_mod_description)],
            ADD_MOD_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_owner_mod_link)],
            ADD_MOD_IMAGE: [MessageHandler(filters.PHOTO, get_owner_mod_image)],
            ADD_MOD_CONFIRM: [CallbackQueryHandler(confirm_add_mod_callback, pattern=\"^(confirm_add_mod_yes|confirm_add_mod_cancel)$\")]
        },
        fallbacks=[CommandHandler(\"start\", start_command), CallbackQueryHandler(lambda u,c: go_to_main_menu_owner(u,c,u.callback_query), pattern=\"^main_menu_\") ],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END # Go back to where it was called from, or end
        }
    )
    
    # Conversation handler for suggesting a mod (user)
    suggest_mod_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(suggest_new_mod_start_callback, pattern=\"^suggest_new_mod_start$\")],
        states={
            SUGGEST_MOD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_mod_name)],
            SUGGEST_MOD_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_mod_description)],
            SUGGEST_MOD_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_user_mod_link)],
            SUGGEST_MOD_IMAGE: [MessageHandler(filters.PHOTO, get_user_mod_image)],
            SUGGEST_MOD_CONFIRM: [CallbackQueryHandler(confirm_suggest_mod_callback, pattern=\"^(confirm_suggest_mod_yes|confirm_suggest_mod_cancel)$\")]
        },
        fallbacks=[CommandHandler(\"start\", start_command)],
         map_to_parent={
            ConversationHandler.END: ConversationHandler.END 
        }
    )

    # Conversation handler for reviewing suggested mods (owner)
    review_mods_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(review_suggested_mods_start_callback, pattern=\"^review_suggested_mods_start$\")],
        states={
            REVIEW_MOD_ACTION: [CallbackQueryHandler(review_action_callback, pattern=\"^review_action_(approve|reject|skip)_.*$\")],
        },
        fallbacks=[CallbackQueryHandler(lambda u,c: go_to_main_menu_owner(u,c,u.callback_query), pattern=\"^main_menu_from_review$\"), CommandHandler(\"start\", start_command)],
        map_to_parent={
            ConversationHandler.END: ConversationHandler.END
        }
    )

    # Conversation handler for managing categories (owner)
    manage_categories_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(manage_categories_menu_callback, pattern=\"^manage_categories_menu$\")],
        states={
            CAT_MANAGE_MENU: [
                CallbackQueryHandler(add_category_start_callback, pattern=\"^add_category_start$\"),
                CallbackQueryHandler(list_all_categories_callback, pattern=\"^list_all_categories$\"),
                CallbackQueryHandler(lambda u,c: go_to_main_menu_owner(u,c,u.callback_query), pattern=\"^main_menu_from_cat_manage$\"),
                CallbackQueryHandler(manage_categories_menu_callback, pattern=\"^manage_categories_menu_from_list$\") # Back to menu
            ],
            ADD_CAT_GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_category_name)],
            ADD_CAT_CONFIRM: [CallbackQueryHandler(confirm_add_category_callback, pattern=\"^(confirm_add_category_yes|confirm_add_category_cancel)$\")]
            # TODO: Add states for edit/delete category if implemented
        },
        fallbacks=[CommandHandler(\"start\", start_command), CallbackQueryHandler(lambda u,c: go_to_main_menu_owner(u,c,u.callback_query), pattern=\"^main_menu_\") ],
         map_to_parent={
            ConversationHandler.END: ConversationHandler.END
        }
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(add_mod_conv_handler)
    application.add_handler(suggest_mod_conv_handler)
    application.add_handler(review_mods_conv_handler)
    application.add_handler(manage_categories_conv_handler)
    application.add_handler(CallbackQueryHandler(view_stats_callback, pattern=\"^view_stats$\"))
    
    # Fallback for unknown commands/messages
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.add_error_handler(error_handler)

    logger.info("Bot starting...")
    application.run_polling()

if __name__ == "__main__":
    main()

