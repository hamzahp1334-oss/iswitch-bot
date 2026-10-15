import logging
from telegram import Update
from telegram.ext import ContextTypes
from database.crud import get_product_by_id, get_setting
from customer_bot.keyboards import cart_keyboard
from services.ui_utils import safe_edit_or_send

logger = logging.getLogger("iswitch.cust.cart")

def get_user_cart(context: ContextTypes.DEFAULT_TYPE) -> dict:
    if "cart" not in context.user_data:
        context.user_data["cart"] = {}
    return context.user_data["cart"]

async def add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pid = int(query.data.replace("cart_add_", ""))
    prod = await get_product_by_id(pid)

    if not prod or prod.get("availability") != "Available":
        await query.answer("Sorry, this item is currently out of stock.", show_alert=True)
        return

    cart = get_user_cart(context)
    curr_qty = cart.get(pid, {}).get("qty", 0)
    stock_qty = prod.get("stock_quantity") or 999

    if curr_qty >= stock_qty:
        await query.answer(f"Cannot add more. Only {stock_qty} in stock.", show_alert=True)
        return

    price = prod.get("discount_price") or prod.get("price") or 0.0
    cart[pid] = {
        "product_id": pid,
        "name": prod["name"],
        "unit_price": price,
        "qty": curr_qty + 1
    }

    await query.answer(f"✅ Added {prod['name']} to cart! (Total: {curr_qty + 1})")

async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    cart = get_user_cart(context)
    delivery_fee_str = await get_setting("delivery_fee", "150")
    try:
        delivery_fee = float(delivery_fee_str)
    except ValueError:
        delivery_fee = 150.0

    cart_items = []
    subtotal = 0.0

    for pid, item in cart.items():
        qty = item["qty"]
        tot = item["unit_price"] * qty
        subtotal += tot
        cart_items.append({
            "product_id": pid,
            "name": item["name"],
            "unit_price": item["unit_price"],
            "quantity": qty,
            "total_price": tot
        })

    currency = await get_setting("currency", "ETB")

    if not cart_items:
        text = "🛒 *Your Cart is Empty*\n\nBrowse products to add items!"
        kb = cart_keyboard([], 0, 0)
    else:
        grand_total = subtotal + delivery_fee
        lines = ["🛒 *Your Cart*\n"]
        for it in cart_items:
            lines.append(f"• *{it['name']}* ({it['quantity']}x) — *{it['total_price']:,.0f} {currency}*")
        
        lines.append(f"\nSubtotal: *{subtotal:,.0f} {currency}*")
        lines.append(f"Delivery: *{delivery_fee:,.0f} {currency}*")
        lines.append(f"💰 *Total: {grand_total:,.0f} {currency}*")
        text = "\n".join(lines)
        kb = cart_keyboard(cart_items, subtotal, delivery_fee)

    await safe_edit_or_send(update, context, text=text, reply_markup=kb)

async def inc_cart_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pid = int(query.data.replace("cart_inc_", ""))
    cart = get_user_cart(context)

    if pid in cart:
        prod = await get_product_by_id(pid)
        stock_qty = prod.get("stock_quantity") or 999 if prod else 999
        if cart[pid]["qty"] < stock_qty:
            cart[pid]["qty"] += 1
            await query.answer("Quantity increased.")
        else:
            await query.answer(f"Max stock reached ({stock_qty}).", show_alert=True)
            return

    await view_cart(update, context)

async def dec_cart_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pid = int(query.data.replace("cart_dec_", ""))
    cart = get_user_cart(context)

    if pid in cart:
        if cart[pid]["qty"] > 1:
            cart[pid]["qty"] -= 1
            await query.answer("Quantity decreased.")
        else:
            del cart[pid]
            await query.answer("Item removed from cart.")

    await view_cart(update, context)

async def remove_cart_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    pid = int(query.data.replace("cart_rem_", ""))
    cart = get_user_cart(context)

    if pid in cart:
        del cart[pid]
        await query.answer("Item removed.")

    await view_cart(update, context)

async def clear_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    context.user_data["cart"] = {}
    await query.answer("Cart cleared.")
    await view_cart(update, context)
