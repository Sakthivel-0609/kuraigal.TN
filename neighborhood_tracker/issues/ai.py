"""
Lightweight, fully offline "AI" helpers for the Government Smart City Portal.

These use keyword/heuristic matching rather than an external LLM API (no API key
required, works instantly, zero cost) - the same approach many production civic-tech
triage systems use for a first-pass classification before human review.

Functions here are deliberately dependency-free (pure Python + the Category model)
so they run fast on every keystroke via AJAX without hitting rate limits.
"""
import re
from collections import Counter

# ---------------------------------------------------------------------------
# Category suggestion - keyword -> category name mapping.
# Matches against Category.name in the database (case-insensitive), so this
# works out of the box with the default fixtures and still degrades gracefully
# if an admin renames/adds categories (falls back to "no suggestion").
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS = {
    'Pothole': ['pothole', 'road damage', 'broken road', 'crack', 'road hole', 'asphalt', 'bumpy road'],
    'Garbage': ['garbage', 'trash', 'waste', 'litter', 'dump', 'rubbish', 'dustbin', 'not collected'],
    'Streetlight': ['streetlight', 'street light', 'lamp post', 'light not working', 'dark street', 'bulb'],
    'Water Leakage': ['water leak', 'pipe burst', 'water pipe', 'leaking water', 'water wastage', 'tap leak'],
    'Drainage': ['drainage', 'drain', 'sewage', 'sewer', 'blocked drain', 'overflow', 'stagnant water'],
    'Stray Animals': ['stray dog', 'stray cattle', 'stray animal', 'cow on road', 'dog bite', 'monkey menace'],
    'Illegal Parking': ['illegal parking', 'parked illegally', 'no parking', 'blocking road', 'double parked'],
}

# ---------------------------------------------------------------------------
# Priority detection - keyword severity buckets.
# ---------------------------------------------------------------------------
PRIORITY_KEYWORDS = {
    'emergency': [
        'fire', 'gas leak', 'explosion', 'collapse', 'collapsed', 'electrocution',
        'electric shock', 'drowning', 'flood', 'accident', 'life threatening',
        'life-threatening', 'building collapse', 'trapped', 'bleeding', 'unconscious',
    ],
    'high': [
        'urgent', 'danger', 'dangerous', 'severe', 'major', 'burst', 'exposed wire',
        'live wire', 'deep hole', 'children at risk', 'school nearby', 'hospital nearby',
        'blind spot', 'no visibility', 'sinking',
    ],
    'medium': [
        'ongoing', 'repeated', 'weeks', 'days', 'growing', 'spreading', 'worsening',
        'complaint again', 'still not fixed',
    ],
}

# ---------------------------------------------------------------------------
# Spam / low-quality detection.
# ---------------------------------------------------------------------------
SPAM_PATTERNS = [
    r'https?://',                          # raw links
    r'\b(?:buy now|click here|free money|earn \$|work from home|casino|viagra)\b',
    r'(.)\1{5,}',                          # aaaaaaaa / !!!!!!!! repeated char spam
    r'^\W+$',                              # only punctuation/symbols
]


def suggest_category(text, categories_queryset):
    """Returns the best-matching Category instance for the given text, or None.
    `categories_queryset` should be the live Category.objects.all() so suggestions
    always reflect whatever categories actually exist in the database."""
    if not text:
        return None
    text_lower = text.lower()
    scores = Counter()
    categories_by_name = {c.name: c for c in categories_queryset}

    for cat_name, keywords in CATEGORY_KEYWORDS.items():
        if cat_name not in categories_by_name:
            continue
        for kw in keywords:
            if kw in text_lower:
                scores[cat_name] += 1

    if not scores:
        return None
    best_name, _count = scores.most_common(1)[0]
    return categories_by_name.get(best_name)


def suggest_priority(text):
    """Returns one of 'emergency', 'high', 'medium', 'low' based on keyword severity."""
    if not text:
        return 'low'
    text_lower = text.lower()

    for level in ('emergency', 'high', 'medium'):
        for kw in PRIORITY_KEYWORDS[level]:
            if kw in text_lower:
                return level
    return 'low'


def is_spam_text(text, min_words=2):
    """Heuristic spam/low-quality check for comments and short text fields."""
    if not text or not text.strip():
        return True
    stripped = text.strip()

    if len(stripped.split()) < min_words and len(stripped) < 6:
        return True

    for pattern in SPAM_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            return True

    # Excessive uppercase shouting (more than 70% caps on a longer message)
    letters = [c for c in stripped if c.isalpha()]
    if len(letters) >= 12:
        upper_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if upper_ratio > 0.7:
            return True

    return False


def generate_summary(text, max_sentences=2):
    """Extractive summary: picks the first sentence plus the sentence containing the
    highest keyword density (category/priority terms) - no external NLP library needed."""
    if not text:
        return ''
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= max_sentences:
        return text.strip()

    all_keywords = set()
    for kws in CATEGORY_KEYWORDS.values():
        all_keywords.update(kws)
    for kws in PRIORITY_KEYWORDS.values():
        all_keywords.update(kws)

    def score(sentence):
        s_lower = sentence.lower()
        return sum(1 for kw in all_keywords if kw in s_lower)

    ranked = sorted(sentences[1:], key=score, reverse=True)
    chosen = [sentences[0]] + ranked[:max_sentences - 1]
    # Keep original order for readability
    chosen_set = set(chosen)
    ordered = [s for s in sentences if s in chosen_set][:max_sentences]
    return ' '.join(ordered)


# ---------------------------------------------------------------------------
# AI Chatbot - simple, fast, fully offline keyword-matched FAQ assistant.
# Each entry: (trigger keywords, response). First match wins, checked in order,
# so more specific triggers are listed before generic ones.
# ---------------------------------------------------------------------------
CHATBOT_CORPUS = [
    (['hi', 'hello', 'hey', 'vanakkam', 'eppadi irukeenga', 'vanga', 'nalla irukeengala',
      'sowkiyama', 'epdi irukeenga', 'yaru nee', 'yaaru nee'],
     "Hello! 👋 I'm the Kuraigal.TN assistant. Ask me how to report an issue, "
     "track a complaint, get emergency numbers, or find department contacts."),

    (['report', 'complain', 'file a complaint', 'submit', 'pandrathu eppadi', 'eppadi podrathu',
      'complaint pannanum', 'issue pota', 'epdi report', 'report pannanum', 'epdi podanum',
      'oru issue potanum', 'problem sollanum', 'eppadi complaint kudukanum', 'naan report pannanum',
      'complaint eppadi kudukurathu', 'problem eppadi sollurathu', 'epdi complaint pannuvathu',
      'issue eppadi kudukurathu', 'puthu complaint', 'puthu issue potanum'],
     "To report an issue: log in, click the '+' Report Issue button (bottom-right), "
     "pick the location on the map, add a title, description and photo, then submit. "
     "Our AI will auto-suggest a category and priority for you."),

    (['track', 'status', 'my complaint', 'where is my', 'enna aachu', 'status enna',
      'eppadi irukku', 'evlo doorathula', 'en complaint enna nadakuthu', 'en issue enge irukku',
      'track pannanum epdi', 'enga irukku en complaint', 'en complaint ku enna aachu',
      'work aachaa', 'solve aachaa', 'fix aachaa', 'mudinjachaa'],
     "You can track your complaints from 'My Profile' - it shows every issue you've "
     "reported along with its current status (Open / In Progress / Resolved) and a "
     "full timeline on each issue's detail page."),

    (['emergency', 'urgent', 'danger', 'fire', 'accident', 'apaayam', 'udhavi pannunga',
      'emergency number', 'help pannunga', 'udhavi venum', 'seekiram vaanga', 'danger irukku',
      'uyir apaayam', 'life risk', 'ambulance venum', 'police venum', 'fire venum'],
     "For a life-threatening emergency, call 108 (Ambulance), 101 (Fire) or 100 (Police) "
     "immediately - don't wait for an online report. You can also mark 'This is dangerous' "
     "when reporting so it's flagged and shown at the top of the issues list."),

    (['department', 'who handles', 'contact', 'yaaru paakuvanga', 'department enna',
      'yaar paapanga', 'entha department', 'yaar responsible', 'yaar solve pannuvanga',
      'department number'],
     "Issues are routed to the relevant department automatically based on category - "
     "for example Water Supply, Electricity Board, or the Municipality's Road Department. "
     "See the Departments section for full contact details."),

    (['point', 'badge', 'leaderboard', 'reward', 'evlo points', 'points evlo', 'evvalavu points',
      'score evlo', 'en score enna', 'points eppadi vaanguvathu', 'points epdi kidaikkum',
      'rank enna', 'top ah irukka epdi'],
     "You earn community points for reporting issues, commenting, and getting upvotes. "
     "Points unlock badges (Bronze/Silver/Gold Reporter, Community Champion) shown on "
     "the Leaderboard page."),

    (['qr', 'scan', 'qr code enna', 'qr code epdi use pandrathu'],
     "Every complaint has a unique QR code on its detail page - scanning it opens that "
     "complaint's page directly, handy for printed notices or sharing offline."),

    (['bookmark', 'save', 'save pandrathu', 'eppadi save pandrathu', 'epdi vachukanum',
      'suudi vaikanum', 'save panna epdi'],
     "Click the Bookmark button on any issue to save it - find all your saved issues "
     "under 'My Bookmarks' in your profile menu."),

    (['language', 'tamil', 'hindi', 'maathanum eppadi', 'tamil la', 'tamil ku maathu',
      'english ku maathu'],
     "You can switch the site language using the dropdown in the top navigation bar - "
     "English and Tamil are available."),

    (['volunteer', 'volunteer aaganum', 'eppadi volunteer aaganum', 'epdi serndhukanum',
      'seva pannanum'],
     "You can register as a community volunteer from the 'Volunteer' page (in your profile "
     "menu) - share your availability and interests, and you'll earn 15 points instantly. "
     "It's for cleanup drives, tree plantation, and awareness campaigns."),

    (['rate officer', 'rating', 'rate the officer', 'rate pandrathu', 'officer ah rate',
      'officer nalla velai pannangala', 'officer ku rating kudukanum'],
     "Once an issue you reported is marked 'Resolved', a star-rating box appears on that "
     "issue's detail page so you can rate the officer's work (1-5 stars) with an optional "
     "comment."),

    (['install', 'app', 'download the app', 'home screen', 'app eppadi', 'phone la eppadi podanum',
      'app eppadi vaikanum', 'app install pandrathu epdi'],
     "This site works as an installable app! Look for an 'Install' icon in your browser's "
     "address bar, or use 'Add to Home Screen' on mobile - it'll work offline too."),

    (['voice', 'speak', 'microphone', 'speech', 'pesi type', 'pesi report',
      'pesi eppadi type pandrathu', 'voice use pandrathu epdi', 'pesi complaint'],
     "On the Report Issue page, there's a 'Voice Input' button next to the Description "
     "field (Chrome/Edge support this) - click it and speak your complaint instead of typing."),

    (['dark mode', 'theme', 'light mode', 'maathrathu eppadi', 'black theme epdi vaikanum',
      'nalla theme'],
     "Toggle Dark/Light mode using the moon/sun icon in the top navigation bar - your "
     "preference is remembered for next time."),

    (['share', 'eppadi share pandrathu', 'share panna epdi', 'friends ku anupanum'],
     "On any issue's detail page, click the 'Share' button to share it via WhatsApp, "
     "Facebook, X (Twitter), Telegram, or copy the direct link."),

    (['heatmap', 'hotspot', 'density', 'adhigam problem eng irukku', 'evlo problem irukku area'],
     "The Heatmap page shows complaint density across the city - green means few issues, "
     "red means many. You can filter it by category too."),

    (['near me', 'nearby', 'arukil irukura', 'pakkathula', 'enakku pakkathula enna problem',
      'aruginla enna irukku', 'aruginla issues'],
     "The 'Nearby' page shows issues close to your current location - allow location "
     "access and choose a radius of 1km, 2km, or 5km."),

    (['duplicate', 'already report', 'already pannirukanga', 'yaravadhu sonnangala',
      'vera yaravadhu report pannirukangala'],
     "When you report an issue, our AI checks nearby complaints of the same category and "
     "warns you if a similar one already exists - you can upvote that one instead of "
     "creating a duplicate."),

    (['feedback', 'suggestion', 'feedback eppadi', 'feedback epdi kudukanum', 'suggestion sollanum'],
     "You can share suggestions or feedback about the portal itself (not a specific issue) "
     "from the 'Feedback' page in your profile menu."),

    (['thank', 'thanks', 'nandri', 'romba nandri', 'romba thanks', 'super', 'semma nalla irukku',
      'santhosham', 'nalla velai'],
     "You're welcome! Let me know if there's anything else I can help with. 🙏"),
]

CHATBOT_FALLBACK = (
    "I'm not sure about that one. Try asking about: reporting an issue, tracking a "
    "complaint, emergency numbers, departments, or community points - English or "
    "Tanglish both work. For anything else, please use the Help Center or Contact page."
)


def _keyword_matches(keyword, text_lower):
    """Short single-word keywords (<=4 chars) match only as whole words, to avoid
    false positives like 'hi' matching inside 'this' or 'which'. Longer keywords
    and multi-word phrases are specific enough to match as plain substrings."""
    if ' ' not in keyword and len(keyword) <= 4:
        return re.search(r'\b' + re.escape(keyword) + r'\b', text_lower) is not None
    return keyword in text_lower


def chatbot_reply(message):
    """Returns a canned response matched by keyword, or a helpful fallback."""
    if not message:
        return CHATBOT_FALLBACK
    text_lower = message.lower()
    for keywords, response in CHATBOT_CORPUS:
        if any(_keyword_matches(kw, text_lower) for kw in keywords):
            return response
    return CHATBOT_FALLBACK
