"""Expeditions: trivia side-quests beyond reading and math.

Six topic worlds, each earning Sparks (a separate points counter from XP)
and a collectible sticker per completed run. This module holds the topic
catalog and a curated offline bank so an expedition always starts
instantly; AI-generated ones brew in the background after the daily-quest
pool is full (see backend engine).

Facts in the offline bank are chosen to be stable — nothing that drifts
with the news cycle. Safety-adjacent topics (chemicals, venom) are framed
as safety knowledge, never instructions.
"""
import random

from . import bank

# key -> (display name, sticker emoji, description used in AI prompts)
TOPICS = {
    "science": ("Science Lab", "🧪",
                "chemistry and physical science — reactions, states of matter, "
                "everyday science like why toothpaste and soap work"),
    "nature": ("Wild World", "🐾",
               "biology, animals, and life science — from venomous snakes to "
               "what plants need to grow"),
    "body": ("Body & Food", "🥦",
             "the human body, nutrition, and health — hydration, vitamins, "
             "why clean water matters"),
    "money": ("Money Matters", "💰",
              "business, money, and economics basics — supply and demand, "
              "stocks, budgets, non-profits vs for-profits"),
    "civics": ("We the People", "🏛️",
               "the U.S. Constitution, how government works, and global "
               "politics and democracy through history"),
    "geo": ("Map Masters", "🗺️",
            "world geography — countries vs cities vs continents, oceans, "
            "capitals, and map lines"),
}

BANK_X = {
    "science": [
        {"category": "science", "type": "mc",
         "question": "You mix baking soda and vinegar and it fizzes like crazy. What is the fizz?",
         "passage": None,
         "options": ["A. Tiny soap bubbles", "B. Carbon dioxide gas being created",
                     "C. Boiling water", "D. Oxygen escaping the vinegar"],
         "answer": "B",
         "explanation": "The acid (vinegar) and base (baking soda) react and create brand-new carbon dioxide gas — the same gas that makes soda fizzy."},
        {"category": "science", "type": "mc",
         "question": "What is H₂O the chemical formula for?",
         "passage": None,
         "options": ["A. Hydrogen peroxide", "B. Salt", "C. Water", "D. Oxygen"],
         "answer": "C",
         "explanation": "H₂O means two hydrogen atoms joined to one oxygen atom — plain water."},
        {"category": "science", "type": "mc",
         "question": "Which state of matter keeps its own shape no matter what container it's in?",
         "passage": None,
         "options": ["A. Solid", "B. Liquid", "C. Gas", "D. All of them"],
         "answer": "A",
         "explanation": "Solids hold their shape; liquids take the shape of their container; gases spread out to fill it completely."},
        {"category": "science", "type": "mc",
         "question": "Cleaning bottles warn: NEVER mix bleach with ammonia. Why?",
         "passage": None,
         "options": ["A. It stains clothing", "B. It creates poisonous gases that can hurt your lungs",
                     "C. It explodes instantly", "D. It ruins the bottle"],
         "answer": "B",
         "explanation": "Mixing them releases toxic chloramine gases — that's why you never mix cleaning chemicals. Knowing what NOT to mix is real chemistry!"},
        {"category": "science", "type": "mc",
         "question": "Why does toothpaste actually protect your teeth?",
         "passage": None,
         "options": ["A. It freezes germs", "B. The minty flavor scares bacteria away",
                     "C. It coats teeth in plastic", "D. Fluoride strengthens enamel while brushing scrubs off plaque"],
         "answer": "D",
         "explanation": "Fluoride rebuilds the mineral armor (enamel) on your teeth, and the scrubbing removes plaque — teamwork of chemistry and cleaning."},
        {"category": "science", "type": "mc",
         "question": "Why does a small amount of chlorine get added to swimming pools?",
         "passage": None,
         "options": ["A. To kill germs in the water", "B. To make the water look blue",
                     "C. To help swimmers float", "D. To keep the water warm"],
         "answer": "A",
         "explanation": "Chlorine destroys bacteria and other germs — pools use more of it than drinking water, which gets just a tiny, safe amount for the same reason."},
    ],
    "nature": [
        {"category": "nature", "type": "mc",
         "question": "Which snake has venom so powerful that one bite could kill many adult humans?",
         "passage": None,
         "options": ["A. Garter snake", "B. Corn snake", "C. Inland taipan", "D. Hognose snake"],
         "answer": "C",
         "explanation": "Australia's inland taipan has the most toxic venom of any land snake — luckily it's shy and bites are extremely rare. The other three are harmless to humans."},
        {"category": "nature", "type": "mc",
         "question": "What does a green plant need to make its own food?",
         "passage": None,
         "options": ["A. Sunlight, water, and carbon dioxide", "B. Only water",
                     "C. Soil and darkness", "D. Sugar sprinkled on its leaves"],
         "answer": "A",
         "explanation": "Photosynthesis uses sunlight for energy to turn water and carbon dioxide into sugar — plants literally make food from light and air."},
        {"category": "nature", "type": "mc",
         "question": "How many hearts does an octopus have?",
         "passage": None,
         "options": ["A. One", "B. Two", "C. Three", "D. Eight"],
         "answer": "C",
         "explanation": "Three! Two pump blood to the gills, one to the rest of the body — and their blood is blue."},
        {"category": "nature", "type": "mc",
         "question": "Which of these animals is a marsupial (carries babies in a pouch)?",
         "passage": None,
         "options": ["A. Kangaroo", "B. Elephant", "C. Penguin", "D. Wolf"],
         "answer": "A",
         "explanation": "Kangaroos, koalas, and opossums are marsupials — their tiny babies finish growing in a pouch."},
        {"category": "nature", "type": "mc",
         "question": "What is a group of wolves called?",
         "passage": None,
         "options": ["A. A herd", "B. A pack", "C. A flock", "D. A school"],
         "answer": "B",
         "explanation": "Wolves live and hunt in packs — herds are for grazing animals, flocks for birds, schools for fish."},
        {"category": "nature", "type": "mc",
         "question": "What do honeybees collect from flowers to make honey?",
         "passage": None,
         "options": ["A. Seeds", "B. Dew drops", "C. Petals", "D. Nectar"],
         "answer": "D",
         "explanation": "Bees sip sugary nectar, carry it home, and transform it into honey — while accidentally spreading pollen that helps plants make seeds."},
    ],
    "body": [
        {"category": "body", "type": "mc",
         "question": "About how much of your body is water?",
         "passage": None,
         "options": ["A. About 10%", "B. About 25%", "C. About 60%", "D. About 95%"],
         "answer": "C",
         "explanation": "Roughly 60% of you is water — it's in your blood, brain, muscles, everywhere. That's why staying hydrated matters so much."},
        {"category": "body", "type": "mc",
         "question": "About how long can a person survive without any water?",
         "passage": None,
         "options": ["A. About 3 hours", "B. About 3 days", "C. About 3 weeks", "D. About 3 months"],
         "answer": "B",
         "explanation": "Only about 3 days. Without water your blood thickens, your kidneys struggle, and your body overheats — you can survive weeks without food, but only days without water."},
        {"category": "body", "type": "mc",
         "question": "Why is a tiny, carefully measured amount of chlorine added to drinking water?",
         "passage": None,
         "options": ["A. To improve the taste", "B. To add vitamins",
                     "C. To kill germs and make the water safe", "D. To make it sparkle"],
         "answer": "C",
         "explanation": "That tiny dose destroys bacteria that could make you sick — one of the biggest health inventions in history. Pools use much more; drinking water uses just a trace."},
        {"category": "body", "type": "mc",
         "question": "Which nutrient is your body's main muscle-building material?",
         "passage": None,
         "options": ["A. Sugar", "B. Protein", "C. Salt", "D. Caffeine"],
         "answer": "B",
         "explanation": "Protein (from foods like beans, eggs, meat, and yogurt) provides the building blocks your body uses to repair and grow muscle."},
        {"category": "body", "type": "mc",
         "question": "How many bones does an adult human have?",
         "passage": None,
         "options": ["A. 86", "B. 106", "C. 206", "D. 406"],
         "answer": "C",
         "explanation": "206! Babies are born with about 300, but many fuse together as you grow."},
        {"category": "body", "type": "mc",
         "question": "Which vitamin does your body make when sunlight hits your skin?",
         "passage": None,
         "options": ["A. Vitamin A", "B. Vitamin C", "C. Vitamin B12", "D. Vitamin D"],
         "answer": "D",
         "explanation": "Sunlight triggers your skin to produce vitamin D, which helps build strong bones — that's why it's nicknamed the sunshine vitamin."},
    ],
    "money": [
        {"category": "money", "type": "mc",
         "question": "What's the big difference between a non-profit and a for-profit business?",
         "passage": None,
         "options": ["A. Non-profits are always smaller",
                     "B. A non-profit puts extra money back into its mission instead of paying owners",
                     "C. For-profits don't pay workers", "D. Non-profits can't have employees"],
         "answer": "B",
         "explanation": "Both can earn money — but a non-profit (like a food bank) must use extra money for its mission, while a for-profit shares profits with its owners."},
        {"category": "money", "type": "mc",
         "question": "Which company was the FIRST in the world to be worth one trillion dollars (in 2018)?",
         "passage": None,
         "options": ["A. Apple", "B. McDonald's", "C. Nike", "D. Disney"],
         "answer": "A",
         "explanation": "Apple hit $1,000,000,000,000 first — that's a one with twelve zeros. Today the biggest companies are worth several trillion."},
        {"category": "money", "type": "mc",
         "question": "A hot new toy is sold out everywhere but everyone wants one. What usually happens to its price?",
         "passage": None,
         "options": ["A. It goes down", "B. It stays exactly the same",
                     "C. It goes up", "D. The toy becomes free"],
         "answer": "C",
         "explanation": "High demand + low supply = higher prices. That's the most famous rule in economics."},
        {"category": "money", "type": "mc",
         "question": "When you own a share of a company's stock, what do you actually own?",
         "passage": None,
         "options": ["A. One of its products", "B. A tiny piece of the company itself",
                     "C. A seat in its office", "D. Its logo"],
         "answer": "B",
         "explanation": "A share is a small slice of ownership — if the company does well, your slice can become more valuable."},
        {"category": "money", "type": "mc",
         "question": "What is a budget?",
         "passage": None,
         "options": ["A. A type of bank account", "B. A loan from your parents",
                     "C. A list of things you can't buy", "D. A plan for how money coming in will be spent or saved"],
         "answer": "D",
         "explanation": "A budget is simply a plan: money in, money out, money saved. Companies, countries, and smart kids all use one."},
        {"category": "money", "type": "mc",
         "question": "Why does a bank pay you interest on savings?",
         "passage": None,
         "options": ["A. It's a reward for letting the bank use your money while it's deposited",
                     "B. It's a tax refund", "C. Banks legally must double your money",
                     "D. It's an apology for long lines"],
         "answer": "A",
         "explanation": "Banks lend out deposited money to other people; interest is your cut for letting them work with yours."},
    ],
    "civics": [
        {"category": "civics", "type": "mc",
         "question": "Was the United States the first democracy? Which place is called the birthplace of democracy?",
         "passage": None,
         "options": ["A. Yes — the United States was first", "B. Ancient Rome",
                     "C. Ancient Athens, in Greece, about 2,500 years ago", "D. Medieval England"],
         "answer": "C",
         "explanation": "Athens let citizens vote on laws around 500 BCE — over 2,000 years before the U.S. The founders borrowed many ideas from Greece and Rome."},
        {"category": "civics", "type": "mc",
         "question": "How many branches does the United States government have?",
         "passage": None,
         "options": ["A. One", "B. Two", "C. Three", "D. Fifty"],
         "answer": "C",
         "explanation": "Three: Congress makes laws (legislative), the President carries them out (executive), and the courts interpret them (judicial). Each checks the others."},
        {"category": "civics", "type": "mc",
         "question": "What are the first ten amendments to the U.S. Constitution called?",
         "passage": None,
         "options": ["A. The Bill of Rights", "B. The Declaration of Independence",
                     "C. The Federalist Papers", "D. The Preamble"],
         "answer": "A",
         "explanation": "The Bill of Rights protects freedoms like speech, press, and fair trials — added in 1791."},
        {"category": "civics", "type": "mc",
         "question": "What is the 'supreme law of the land' in the United States?",
         "passage": None,
         "options": ["A. The President's orders", "B. The Constitution",
                     "C. State laws", "D. The Supreme Court's opinions"],
         "answer": "B",
         "explanation": "Every law and every leader must follow the Constitution — that's why changing it takes a huge nationwide effort."},
        {"category": "civics", "type": "mc",
         "question": "About how many countries are there in the world today?",
         "passage": None,
         "options": ["A. About 50", "B. About 95", "C. About 195", "D. About 500"],
         "answer": "C",
         "explanation": "About 195 — 193 belong to the United Nations. The number changes only rarely, when new countries form."},
        {"category": "civics", "type": "mc",
         "question": "In the U.S., who signs a bill from Congress to make it a law?",
         "passage": None,
         "options": ["A. The Supreme Court", "B. The Speaker of the House",
                     "C. The state governors", "D. The President"],
         "answer": "D",
         "explanation": "After both houses of Congress pass a bill, the President signs it into law — or vetoes it, which Congress can override with a big enough vote."},
    ],
    "geo": [
        {"category": "geo", "type": "mc",
         "question": "Which of these is a COUNTRY (not a city or a continent)?",
         "passage": None,
         "options": ["A. Africa", "B. Japan", "C. Paris", "D. Asia"],
         "answer": "B",
         "explanation": "Japan is a country. Africa and Asia are continents (which contain many countries), and Paris is a city in the country of France."},
        {"category": "geo", "type": "mc",
         "question": "What is the largest ocean on Earth?",
         "passage": None,
         "options": ["A. Atlantic", "B. Indian", "C. Arctic", "D. Pacific"],
         "answer": "D",
         "explanation": "The Pacific covers about a third of the planet — bigger than all the land on Earth combined."},
        {"category": "geo", "type": "mc",
         "question": "The Sahara Desert is on which continent?",
         "passage": None,
         "options": ["A. Africa", "B. South America", "C. Australia", "D. Europe"],
         "answer": "A",
         "explanation": "The Sahara stretches across northern Africa — it's nearly as big as the entire United States."},
        {"category": "geo", "type": "mc",
         "question": "What is the capital of the United States?",
         "passage": None,
         "options": ["A. New York City", "B. Los Angeles", "C. Washington, D.C.", "D. Chicago"],
         "answer": "C",
         "explanation": "Washington, D.C. — 'D.C.' means District of Columbia, a special zone that isn't part of any state."},
        {"category": "geo", "type": "mc",
         "question": "What imaginary line divides Earth into the Northern and Southern Hemispheres?",
         "passage": None,
         "options": ["A. The prime meridian", "B. The equator",
                     "C. The international date line", "D. The Tropic of Cancer"],
         "answer": "B",
         "explanation": "The equator circles the middle of the Earth at 0° latitude — countries on it have warm weather all year."},
        {"category": "geo", "type": "mc",
         "question": "Which country has the most people in the world?",
         "passage": None,
         "options": ["A. United States", "B. Russia", "C. India", "D. Brazil"],
         "answer": "C",
         "explanation": "India passed China in 2023 — over 1.4 billion people, more than four times the U.S. population."},
    ],
}


def valid_question(q):
    """Like bank.valid_question, but for expedition topics."""
    if not isinstance(q, dict):
        return False
    if q.get("category") not in TOPICS:
        return False
    if q.get("type") != "mc":
        return False
    if not q.get("question") or not q.get("answer"):
        return False
    if len(q.get("options") or []) != 4:
        return False
    return True


# Stable ids so completed trivia doesn't repeat (same scheme as the bank).
for _topic_questions in BANK_X.values():
    for _q in _topic_questions:
        _q["id"] = bank.question_id(_q)


def sample(topic, n, mastered=()):
    """Pick n offline questions for a topic: unseen first, then topped up
    from already-mastered ones so an expedition is never short — the small
    bank is only a bridge until AI-brewed sets for the topic arrive."""
    mastered = set(mastered)
    pool = BANK_X[topic]
    fresh = [q for q in pool if q["id"] not in mastered]
    seen = [q for q in pool if q["id"] in mastered]
    random.shuffle(fresh)
    random.shuffle(seen)
    return (fresh + seen)[:n]
