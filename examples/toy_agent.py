"""A stand-in agent loop you can trap without any API keys.

    aitrap run -- python examples/toy_agent.py
    aitrap trap examples.toy_agent.apply_discount
    aitrap poll 0

It carries a deliberate bug: apply_discount is handed the post-discount subtotal, so a
coupon that should qualify never does. You find it by reading the live values, not the source.
"""
import asyncio
import random


class Coupon:
    def __init__(self, code, min_spend, percent):
        self.code, self.min_spend, self.percent = code, min_spend, percent


async def call_model(prompt, temperature=0.2):
    await asyncio.sleep(0.15)
    return {"text": f"answer to {prompt[:24]}", "tokens": random.randint(40, 200)}


def apply_discount(coupon, base_amount, items):
    eligible = base_amount >= coupon.min_spend
    return base_amount * coupon.percent / 100 if eligible else 0.0


def price_order(gross_subtotal, member_discount, coupon, customer_email):
    net_subtotal = gross_subtotal - member_discount
    promo = apply_discount(coupon, net_subtotal, [])   # bug: net, should be gross
    return round(net_subtotal - promo, 2)


async def handle_turn(turn, coupon):
    await call_model(f"user said: {turn}")
    total = price_order(628.49, 62.85, coupon, "someone@example.com")
    print(f"[agent] {turn!r} -> total {total}", flush=True)


async def main():
    coupon = Coupon("SAVE15", 600.0, 15.0)
    turns = ["what's my total?", "apply my coupon", "is shipping free?"]
    while True:
        for turn in turns:
            await handle_turn(turn, coupon)
            await asyncio.sleep(1.5)


if __name__ == "__main__":
    asyncio.run(main())
