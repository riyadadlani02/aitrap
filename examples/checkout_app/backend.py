"""Checkout backend with a real pricing bug, for the phone demo. Standard library only.

    aitrap run -- python examples/checkout_app/backend.py
    aitrap trap examples.checkout_app.backend.OrderPricingPipeline.calculate_order
    open http://127.0.0.1:8000/

Tap Apply on the phone and the trap fires while the server keeps serving. The bug is
that the coupon's minimum-spend check is handed the POST-discount subtotal, so a cart
that qualifies is told it doesn't. You cannot see that in the source; the two amounts
only differ at runtime.
"""
import json
import os
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# The demo ships broken on purpose. CHECKOUT_FIXED=1 applies the two-line repair so the
# before and after can both be recorded from this one file.
FIXED = os.environ.get("CHECKOUT_FIXED") == "1"

HERE = pathlib.Path(__file__).parent

CART = [
    {"name": "Studio Wireless Pro Headphones", "cat": "Audio", "qty": 1, "price": 299.99},
    {"name": "Apex Smart Fitness Watch", "cat": "Wearables", "qty": 1, "price": 199.50},
    {"name": "MechPro Wireless Keyboard", "cat": "Accessories", "qty": 1, "price": 129.00},
]
COUPONS = {
    "TECH15": {"code": "TECH15", "min_spend": 600.00, "percent": 15.0},
    "AUDIO20": {"code": "AUDIO20", "min_spend": 250.00, "percent": 20.0},
}
TIERS = {"GOLD": 10.0, "SILVER": 5.0, "NONE": 0.0}


class TierDiscountService:
    def compute_discount(self, tier, gross_amount):
        return round(gross_amount * TIERS.get(tier, 0.0) / 100, 2)


class PromoCouponEngine:
    def evaluate_promo(self, coupon, base_amount, items):
        """base_amount is what the caller says to test against min_spend."""
        eligible_spend = base_amount
        if eligible_spend < coupon["min_spend"]:
            return 0.0, f"Coupon '{coupon['code']}' requires min spend of ${coupon['min_spend']:.2f}."
        return round(eligible_spend * coupon["percent"] / 100, 2), None


class ShippingRateProvider:
    def calculate_shipping(self, subtotal, express):
        free_over = 600.00
        if express and subtotal < free_over:
            return 25.00
        return 0.00


class OrderPricingPipeline:
    def __init__(self):
        self.tier_service = TierDiscountService()
        self.promo_engine = PromoCouponEngine()
        self.shipping = ShippingRateProvider()

    def calculate_order(self, items, tier, coupon, express):
        gross_subtotal = round(sum(i["price"] * i["qty"] for i in items), 2)
        member_discount = self.tier_service.compute_discount(tier, gross_subtotal)
        net_subtotal = round(gross_subtotal - member_discount, 2)

        # The bug: eligibility is meant to be judged on what the customer spent
        # (gross_subtotal), but the post-discount figure is passed instead.
        promo_base = gross_subtotal if FIXED else net_subtotal
        promo_discount, promo_error = self.promo_engine.evaluate_promo(
            coupon, promo_base, items) if coupon else (0.0, None)

        taxable = round(net_subtotal - promo_discount, 2)
        tax = round(taxable * 0.085, 2)
        shipping_fee = self.shipping.calculate_shipping(
            gross_subtotal if FIXED else net_subtotal, express)
        total = round(taxable + tax + shipping_fee, 2)
        return {
            "items": items,
            "grossSubtotal": gross_subtotal,
            "memberDiscount": member_discount,
            "tier": tier,
            "promoDiscount": promo_discount,
            "promoError": promo_error,
            "tax": tax,
            "shipping": shipping_fee,
            "total": total,
        }


PIPELINE = OrderPricingPipeline()


class CartViewModel:
    """Entry point for a tap on the phone - the first frame worth trapping."""

    def on_apply_tapped(self, coupon_code, express, tier="GOLD"):
        coupon = COUPONS.get((coupon_code or "").strip().upper())
        if coupon_code and not coupon:
            return {"error": f"No such coupon '{coupon_code}'."}
        return PIPELINE.calculate_order(CART, tier, coupon, express)


VIEW_MODEL = CartViewModel()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_):
        pass

    def _send(self, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/checkout"):
            from urllib.parse import parse_qs, urlparse
            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            return self._send(VIEW_MODEL.on_apply_tapped(
                q.get("coupon", ""), q.get("express") == "1", q.get("tier", "GOLD")))
        page = HERE / "index.html"
        return self._send(page.read_bytes(), "text/html; charset=utf-8")


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("[checkout] http://127.0.0.1:8000/", flush=True)
    srv.serve_forever()
