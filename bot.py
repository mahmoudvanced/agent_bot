import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from textwrap import wrap  # Add to your imports

def format_choice(choice: str) -> str:
    """Formats long choices with smart line breaks"""
    # Prefer breaking by punctuation first
    for delimiter in [". ", ", ", "; ", " - "]:
        if delimiter in choice:
            parts = choice.split(delimiter)
            # Add the delimiter back if it's needed to make sense
            parts = [p + delimiter.strip() for p in parts[:-1]] + [parts[-1]]
            return "\n".join(wrap(" ".join(parts), width=30))
    
    # If no delimiter found, wrap by character limit
    return "\n".join(wrap(choice, width=30))

def format_answer_response(is_correct: bool, answer: str) -> str:
    """Formats quiz answers with proper line breaks"""
    # Handle answers with ellipses
    if "..." in answer:
        parts = answer.split("...")
        formatted_answer = "...\n".join(parts)
    else:
        formatted_answer = answer
    
    # Split long answers (more than 50 chars)
    if len(formatted_answer) > 50:
        formatted_answer = "\n".join([formatted_answer[i:i+50] for i in range(0, len(formatted_answer), 50)])
    
    return (
        f"✅ Correct!\n\n{formatted_answer}" 
        if is_correct 
        else f"❌ Wrong!\n\nCorrect answer:\n{formatted_answer}"
    )
# Load all questions
with open('quiz.json', 'r') as f:
    all_questions = json.load(f)

# Global variables
user_scores = {}  # {user_id: {"name": str, "correct": int, "total": int}}
active_quizzes = {}  # {chat_id: {"questions": list, "current_index": int, "user_id": int}}

def initialize_user(user_id: int, user_name: str):
    """Ensure a user exists in the scoring system"""
    if user_id not in user_scores:
        user_scores[user_id] = {
            "name": user_name,
            "correct": 0,
            "total": 0
        }

from telegram import constants


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    initialize_user(user.id, user.full_name)
    
    await update.message.reply_text(
        f"🧠 Welcome {user.full_name} to the Complete Quiz Bot!\n\n"
        "⚡ Automatic progression through all questions\n"
        "🔄 Questions will be randomized\n"
        "📊 /score - Check your progress\n"
        "🏆 /leaderboard - See top players\n\n"
        "Click /startquiz to begin!"
    )

async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a new quiz session with all questions"""
    user = update.effective_user
    initialize_user(user.id, user.full_name)
    
    chat_id = update.effective_chat.id
    
    # Create randomized quiz
    quiz_questions = all_questions.copy()
    random.shuffle(quiz_questions)
    
    active_quizzes[chat_id] = {
        "questions": quiz_questions,
        "current_index": 0,
        "user_id": user.id
    }
    
    # Start first question
    await ask_question(chat_id, context)

async def ask_question(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    quiz_data = active_quizzes.get(chat_id)
    if not quiz_data:
        return

    question = quiz_data["questions"][quiz_data["current_index"]]
    
    # Truncate option text in buttons
    keyboard = []
    full_options_preview = ""
    for i, option in enumerate(question['options']):
        preview_text = option if len(option) <= 30 else option[:27] + "..."
        full_options_preview += f"{i+1}. {option}\n"
        keyboard.append([
            InlineKeyboardButton(preview_text, callback_data=f"ans_{i}")
        ])
    
    # Store correct answer index
    correct_idx = question['options'].index(question['correct'])
    active_quizzes[chat_id]["correct_idx"] = correct_idx

    await context.bot.send_message(
        chat_id,
        f"Question {quiz_data['current_index'] + 1}/{len(quiz_data['questions'])}\n\n"
        f"❓ {question['text']}\n\n"
        f"{full_options_preview}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user's answer"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    # Initialize user if not exists
    initialize_user(user.id, user.full_name)
    
    if chat_id not in active_quizzes:
        await query.edit_message_text("Quiz session expired. Start a new one with /startquiz")
        return
    
    quiz_data = active_quizzes[chat_id]
    question = quiz_data["questions"][quiz_data["current_index"]]
    
    # Process answer
    try:
        answer_idx = int(query.data.split("_")[1])
        correct_idx = quiz_data["correct_idx"]
        is_correct = (answer_idx == correct_idx)
        
        # Update scores
        user_scores[user.id]["total"] += 1
        if is_correct:
            user_scores[user.id]["correct"] += 1
        
        # Get formatted response
        response = format_answer_response(is_correct, question['correct'])
        
        # Add progress info
        progress = f"\n\n📊 Score: {user_scores[user.id]['correct']}/{user_scores[user.id]['total']}"
        
        await query.edit_message_text(
            f"{response}{progress}\n\n"
            f"Next question loading..."
        )
        
        # Move to next question
        quiz_data["current_index"] += 1
        await ask_question(chat_id, context)
        
    except (ValueError, IndexError, KeyError) as e:
        print(f"Error processing answer: {e}")
        await query.edit_message_text("Error processing your answer. Please try again.")
async def show_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's current score"""
    user = update.effective_user
    initialize_user(user.id, user.full_name)
    
    score = user_scores[user.id]
    total_questions = len(all_questions)
    answered = score["total"]
    remaining = total_questions - answered
    
    accuracy = (score["correct"]/answered*100) if answered > 0 else 0
    
    await update.message.reply_text(
        f"📊 {user.full_name}'s Progress:\n"
        f"Correct: {score['correct']}\n"
        f"Answered: {answered}/{total_questions}\n"
        f"Remaining: {remaining}\n"
        f"Accuracy: {accuracy:.1f}%"
    )

async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display leaderboard"""
    if not user_scores:
        await update.message.reply_text("No scores yet! Be the first to play!")
        return
    
    sorted_scores = sorted(
        user_scores.values(),
        key=lambda x: (-x["correct"], x["total"])
    )[:10]
    
    leaderboard_text = "🏆 Leaderboard 🏆\n\n"
    for rank, score in enumerate(sorted_scores, 1):
        accuracy = (score["correct"]/score["total"]*100) if score["total"] > 0 else 0
        leaderboard_text += (
            f"{rank}. {score['name']}: "
            f"{score['correct']}/{score['total']} "
            f"({accuracy:.1f}%)\n"
        )
    
    await update.message.reply_text(leaderboard_text)

def main():
    """Start the bot"""
    app = Application.builder().token("7469506162:AAHX5JtEE1WMyxIbz--utvEsijtrMNiZ4P8").build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("startquiz", start_quiz))
    app.add_handler(CommandHandler("score", show_score))
    app.add_handler(CommandHandler("leaderboard", show_leaderboard))
    app.add_handler(CallbackQueryHandler(handle_answer, pattern="^ans_"))
    
    app.run_polling()

if __name__ == "__main__":
    main()
