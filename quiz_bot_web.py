"""
Telegram Quiz Bot
==================
يحوّل نصوص أسئلة بصيغة معينة إلى Quiz Polls تفاعلية على تيليجرام.

صيغة النص المطلوبة:
--------------------
* نص السؤال
  +خيار أول
  +خيار صحيح=
  +خيار ثالث
  +خيار رابع

- كل سؤال يبدأ بعلامة "*"
- كل خيار يبدأ بعلامة "+"
- الخيار الصحيح ينتهي بعلامة "="
- ممكن أكثر من سؤال في نفس الرسالة

المكتبة المستخدمة: python-telegram-bot v20+ (async)

خطوات التشغيل:
---------------
1) ثبّت المكتبة:
   pip install python-telegram-bot --upgrade

2) اذهب إلى @BotFather على تيليجرام وأنشئ بوت جديد بأمر /newbot
   وخذ الـ TOKEN الذي يعطيك إياه.

3) ضع التوكن في متغير البيئة، أو استبدله مباشرة في المتغير BOT_TOKEN أدناه:
   export BOT_TOKEN="1234567890:ABC..."   (على Linux/Mac)
   set BOT_TOKEN=1234567890:ABC...        (على Windows)

4) شغّل الملف:
   python quiz_bot.py

5) للتشغيل المجاني 24/7 يمكنك رفعه على Render.com أو Railway أو أي VPS بسيط،
   أو استخدام Webhook بدلاً من polling إذا كنت على استضافة serverless.
"""

import os
import re
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# الإعدادات
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN", "ضع_التوكن_هنا")

MAX_OPTION_LENGTH = 100          # حد تيليجرام لطول كل خيار في الـ poll
MAX_QUESTION_LENGTH = 300        # حد تيليجرام لطول نص السؤال

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# دالة تحليل النص واستخراج الأسئلة
# ---------------------------------------------------------------------------

def parse_questions(raw_text: str):
    """
    تأخذ النص الخام وتُرجع قائمة من القواميس، كل قاموس يمثل سؤالاً:
    {
        "question": "نص السؤال",
        "options": ["خيار1", "خيار2", ...],
        "correct_index": 1
    }

    ترفع ValueError مع رسالة توضيحية إذا كانت الصيغة غير صحيحة.
    """
    questions = []

    # نقسّم النص إلى كتل بناءً على علامة "*" (كل كتلة = سؤال واحد)
    # نتجاهل أي شيء قبل أول "*"
    blocks = raw_text.split("*")
    blocks = [b.strip() for b in blocks if b.strip()]

    if not blocks:
        raise ValueError(
            "لم أجد أي سؤال في النص. تأكد أن كل سؤال يبدأ بعلامة *"
        )

    for block_num, block in enumerate(blocks, start=1):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]

        if not lines:
            continue

        # أول سطر هو نص السؤال (قد يمتد لأكثر من سطر قبل أول "+")
        question_lines = []
        option_lines = []
        seen_option = False

        for ln in lines:
            if ln.startswith("+"):
                seen_option = True
                option_lines.append(ln)
            elif not seen_option:
                question_lines.append(ln)
            # أي سطر بعد بدء الخيارات ولا يبدأ بـ "+" يُتجاهل (سطر فارغ أو ملاحظة)

        question_text = " ".join(question_lines).strip()

        if not question_text:
            raise ValueError(
                f"السؤال رقم {block_num}: لم أجد نص سؤال قبل الخيارات.\n"
                "تأكد من كتابة نص السؤال مباشرة بعد علامة *"
            )

        if len(option_lines) < 2:
            raise ValueError(
                f"السؤال رقم {block_num} ('{question_text[:40]}...'):\n"
                "لازم يكون فيه خياران على الأقل يبدآن بعلامة +"
            )

        options = []
        correct_index = None

        for i, opt_line in enumerate(option_lines):
            # نشيل علامة "+" من البداية
            opt_text = opt_line[1:].strip()

            is_correct = False
            # الخيار الصحيح ينتهي بعلامة "="
            if opt_text.endswith("="):
                is_correct = True
                opt_text = opt_text[:-1].strip()

            if not opt_text:
                raise ValueError(
                    f"السؤال رقم {block_num}: أحد الخيارات فارغ بعد إزالة الرموز."
                )

            if len(opt_text) > MAX_OPTION_LENGTH:
                opt_text = opt_text[:MAX_OPTION_LENGTH]

            options.append(opt_text)

            if is_correct:
                if correct_index is not None:
                    raise ValueError(
                        f"السؤال رقم {block_num} ('{question_text[:40]}...'):\n"
                        "فيه أكتر من خيار محدد كإجابة صحيحة (أكتر من علامة =).\n"
                        "لازم يكون فيه إجابة صحيحة واحدة بس."
                    )
                correct_index = i

        if correct_index is None:
            raise ValueError(
                f"السؤال رقم {block_num} ('{question_text[:40]}...'):\n"
                "لم أجد أي خيار محدد كإجابة صحيحة. تأكد إن الخيار الصحيح ينتهي بعلامة ="
            )

        if len(options) > 10:
            raise ValueError(
                f"السؤال رقم {block_num}: تيليجرام يسمح بحد أقصى 10 خيارات فقط لكل سؤال."
            )

        if len(question_text) > MAX_QUESTION_LENGTH:
            question_text = question_text[:MAX_QUESTION_LENGTH]

        questions.append(
            {
                "question": question_text,
                "options": options,
                "correct_index": correct_index,
            }
        )

    return questions


# ---------------------------------------------------------------------------
# أوامر ومعالجات البوت
# ---------------------------------------------------------------------------

WELCOME_MESSAGE = (
    "أهلاً بيك! 👋\n\n"
    "أنا بوت بحوّل أي أسئلة اختيار من متعدد لكويز تفاعلي (Quiz Poll) على تيليجرام.\n\n"
    "📝 *الصيغة المطلوبة:*\n"
    "ابعت رسالة بالشكل ده:\n\n"
    "```\n"
    "* ما هي عاصمة مصر؟\n"
    "+الإسكندرية\n"
    "+القاهرة=\n"
    "+أسوان\n"
    "+الأقصر\n"
    "```\n\n"
    "*ملاحظات مهمة:*\n"
    "• كل سؤال يبدأ بعلامة \\* \n"
    "• كل خيار يبدأ بعلامة \\+ \n"
    "• الخيار الصحيح لازم ينتهي بعلامة = \n"
    "• تقدر تبعت أكتر من سؤال في نفس الرسالة، كل سؤال يبدأ بـ \\* جديدة\n\n"
    "📌 *مثال لأكتر من سؤال مرة واحدة:*\n"
    "```\n"
    "* 2 + 2 = ؟\n"
    "+3\n"
    "+4=\n"
    "+5\n"
    "\n"
    "* لون السماء؟\n"
    "+أحمر\n"
    "+أزرق=\n"
    "+أخضر\n"
    "```\n\n"
    "جرّب دلوقتي وابعتلي أي أسئلة! 🚀"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /start يرحب بالمستخدم ويشرح طريقة الاستخدام."""
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """أمر /help يعرض نفس شرح /start."""
    await update.message.reply_text(WELCOME_MESSAGE, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يستقبل أي رسالة نصية عادية، يحللها، ويرسل الأسئلة كـ Quiz Polls."""
    raw_text = update.message.text

    if not raw_text or "*" not in raw_text:
        await update.message.reply_text(
            "❌ ما لقيتش أي سؤال في الرسالة.\n\n"
            "لازم يبدأ كل سؤال بعلامة *\n"
            "ابعت /start عشان تشوف مثال كامل على الصيغة الصحيحة."
        )
        return

    try:
        questions = parse_questions(raw_text)
    except ValueError as e:
        await update.message.reply_text(
            f"⚠️ في مشكلة في صيغة الرسالة:\n\n{e}\n\n"
            "ابعت /start لو عايز تشوف مثال صحيح."
        )
        return
    except Exception as e:
        logger.exception("خطأ غير متوقع أثناء تحليل النص")
        await update.message.reply_text(
            "❌ حصل خطأ غير متوقع أثناء تحليل الرسالة. "
            "تأكد من الصيغة وحاول تاني، أو ابعت /start للمثال."
        )
        return

    sent_count = 0
    for q in questions:
        try:
            await update.message.reply_poll(
                question=q["question"],
                options=q["options"],
                type="quiz",
                correct_option_id=q["correct_index"],
                is_anonymous=False,
            )
            sent_count += 1
        except Exception as e:
            logger.exception("خطأ أثناء إرسال الـ poll")
            await update.message.reply_text(
                f"⚠️ ما قدرتش أبعت السؤال: '{q['question'][:50]}...'\n"
                f"السبب المحتمل: {e}"
            )

    if sent_count == 0:
        await update.message.reply_text(
            "❌ ما اتبعتش أي سؤال. راجع الصيغة وحاول تاني."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج عام لأي أخطاء غير متوقعة في البوت."""
    logger.error("حصل استثناء أثناء معالجة تحديث:", exc_info=context.error)


# ---------------------------------------------------------------------------
# تشغيل البوت
# ---------------------------------------------------------------------------

def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "ضع_التوكن_هنا":
        raise SystemExit(
            "لازم تحط التوكن الخاص بالبوت أولاً!\n"
            "استخدم متغير البيئة BOT_TOKEN أو عدّل القيمة في أعلى الملف."
        )

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_error_handler(error_handler)

    # Render (وأي استضافة Web Service مجانية مشابهة) بتوفر متغيرات البيئة دي
    # تلقائياً: PORT (البورت اللي لازم نسمع عليه) وRENDER_EXTERNAL_URL
    # (الرابط العام بتاع الخدمة). لو مش موجودين (يعني بنشغل الملف على
    # جهازنا الشخصي)، البوت هيشتغل بطريقة polling العادية بدل webhook.
    port = os.environ.get("PORT")
    external_url = os.environ.get("RENDER_EXTERNAL_URL")

    if port and external_url:
        webhook_path = BOT_TOKEN  # جزء سري في الرابط عشان محدش غير تيليجرام يقدر يبعتلنا عليه
        webhook_url = f"{external_url}/{webhook_path}"
        logger.info("البوت شغّال دلوقتي عن طريق webhook: %s", webhook_url)
        application.run_webhook(
            listen="0.0.0.0",
            port=int(port),
            url_path=webhook_path,
            webhook_url=webhook_url,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("البوت شغّال دلوقتي عن طريق polling... (Ctrl+C للإيقاف)")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
