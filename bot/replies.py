"""Comment understanding and reply texts for the B1 Trainer Instagram bot.

Everything here is plain data and pure functions, so it can be tested without the API.
Texts exist in the 8 app languages; the commenter's language is guessed from the comment,
falling back to the language of the post.
"""
import random
import re
import unicodedata

LANGS = ('de', 'en', 'tr', 'ar', 'uk', 'ru', 'fa', 'ro')

# ---------------------------------------------------------------- language guess
WORDS = {
    'de': 'ich du und nicht danke super toll ist das die der wie wo gibt es kostet auch mit für bitte gut sehr prüfung habe morgen',
    'en': 'the and thanks thank you is are please how where what great nice love this can it for good very cool',
    'tr': 've bir için nasıl nerede teşekkürler teşekkür ederim çok güzel harika ne kadar fiyat ücretsiz mi var bu da bağlantı lütfen hocam bak buna şuna bunu sınav sınavım',
    'ro': 'și si pentru mulțumesc multumesc mersi cât cat costă costa este aplicația aplicatia foarte bine super unde',
}
UK_WORDS = set('дякую дуже будь ласка як де скільки що це мені прошу посилання привіт добре так чудово'.split())
RU_WORDS = set('спасибо очень пожалуйста как где сколько что это мне прошу ссылка привет хорошо да отлично'.split())
CHARS = {
    'tr': 'ğışİĞŞ',
    'ro': 'ățșĂȚȘ',
    'de': 'äöüßÄÖÜ',
}


def detect_lang(text, fallback='de'):
    t = text or ''
    if re.search('[؀-ۿ]', t):
        return 'fa' if re.search('[پچژگکی]', t) else 'ar'
    if re.search('[Ѐ-ӿ]', t):
        low = t.lower()
        words = re.findall(r'\w+', low)
        uk = 2 * len(re.findall('[іїєґ]', low)) + sum(w in UK_WORDS for w in words)
        ru = 2 * len(re.findall('[ыэъё]', low)) + sum(w in RU_WORDS for w in words)
        return 'uk' if uk > ru else 'ru'
    low = t.lower()
    tokens = re.findall(r"[a-zäöüßğışçăâîțș']+", low)
    score = {k: 0 for k in ('de', 'en', 'tr', 'ro')}
    for k, w in WORDS.items():
        ws = set(w.split())
        score[k] += sum(1 for x in tokens if x in ws)
    for k, cs in CHARS.items():
        score[k] += 2 * sum(1 for c in t if c in cs)
    best = max(score, key=score.get)
    return best if score[best] > 0 else fallback


# ---------------------------------------------------------------- intents
def _rx(words):
    return re.compile('|'.join(words), re.I)

SPAM = _rx([r'https?://', r'www\.', r'\.(com|net|io|ru|xyz)/', r'\bdm (me|us)\b', r'check (my|our) (page|profile|bio)',
            r'\bpromo', r'\bcollab', r'follow ?back', r'\bf4f\b', r'crypto', r'bitcoin', r'forex', r'earn \$', r'onlyfans',
            r'send (it|pic)s? to @', r'\bpromote (it|your)'])
NEGATIVE = _rx([r'betrug', r'abzocke', r'\bscam', r'\bfake\b', r'\bmüll\b', r'schei(ß|ss)e', r'dolandır', r'sahtekar',
                r'мошен', r'развод', r'шахрай', r'احتيال', r'نصاب', r'کلاهبردار', r'țeapă', r'teapa', r'înșelătorie'])
LINK = _rx([r'\blink', r'\blinki', r'bağlantı', r'\bindir', r'download', r'herunterlad', r'play ?store', r'google play',
            r'wie heißt die app', r'name der app', r'uygulama(nın)? ad', r'what.?s the app', r'where can i (get|find)',
            r'ссылк', r'посилан', r'رابط', r'لينك', r'لینک', r'\blinkul',
            r'welche app', r'ich will die app', r'die app (haben|holen)', r'^\W*app\W*$', r'(need|want|get) (the|this) app',
            r'скачать', r'завантаж', r'تحميل', r'دانلود', r'descarc', r'yükle'])
FAQ = [
    ('ios', _rx([r'iphone', r'ipad', r'\bios\b', r'apple', r'app ?store', r'айфон', r'آیفون', r'ايفون'])),
    ('price', _rx([r'preis', r'kostet', r'kosten', r'kostenlos', r'gratis', r'\babo', r'\bprice', r'\bcost', r'\bfree\b',
                   r'fiyat', r'ücret', r'kaç para', r'paralı', r'цена', r'стоит', r'бесплат', r'ціна', r'коштує', r'безкоштов',
                   r'سعر', r'مجان', r'قیمت', r'رایگان', r'هزینه', r'preț', r'\bpret', r'costă', r'gratuit'])),
    ('official', _rx([r'offiziell', r'official', r'\btelc\b', r'resmi', r'офиц', r'офіц', r'رسمي', r'رسمی', r'oficial'])),
    ('oral', _rx([r'mündlich', r'sprechen', r'\boral\b', r'speaking', r'sözlü', r'konuşma', r'устн', r'усн', r'شفهي', r'شفاهی'])),
    ('offline', _rx([r'offline', r'internet', r'çevrimdışı', r'офлайн', r'интернет', r'інтернет', r'دون اتصال', r'آفلاین'])),
]
EXAM = _rx([r'prüfung', r'\bexam', r'sınav', r'экзамен', r'іспит', r'امتحان', r'آزمون', r'examen'])
QUESTION = re.compile(r'\?|؟|\b(wie|wo|was|wann|warum|how|where|what|when|why|nasıl|nerede|ne zaman|neden|как|где|когда|почему|як|де|коли|чому|كيف|أين|متى|چطور|کجا|کی|cum|unde|când)\b', re.I)


def quiz_answer(text, words):
    """Returns 'a'/'b'/'c' if the comment answers a quiz, else None.
    Accepts "b", "B)", "b) Deshalb", "Antwort: c", or just the option word ("deshalb")."""
    t = (text or '').strip().lower()
    t = unicodedata.normalize('NFC', t)
    m = re.match(r'^(?:antwort|answer|cevap)?\s*[:\-]?\s*([abc])(?:\)|\.|:|\s|$|!)', t)
    if m:
        return m.group(1)
    bare = re.sub(r'[^\w äöüß]', '', t).strip()
    for k, w in zip('abc', words):              # the whole comment is exactly one option
        if bare == w.lower():
            return k
    if len(t.split()) <= max(3, max(len(w.split()) for w in words) + 2):
        hits = [k for k, w in zip('abc', words) if re.search(r'(^|[^a-zäöüß])' + re.escape(w.lower()) + r'($|[^a-zäöüß])', t)]
        if len(hits) == 1:
            return hits[0]
    return None


def classify(text, post):
    """-> (intent, detail). intents: spam, negative, link, quiz, faq, question, exam, generic, empty."""
    t = (text or '').strip()
    if not t:
        return 'empty', None
    if SPAM.search(t):
        return 'spam', None
    if NEGATIVE.search(t):
        return 'negative', None
    if post and post.get('kind') == 'quiz':
        a = quiz_answer(t, post['quiz']['words'])
        if a:
            return 'quiz', a
    if LINK.search(t):
        return 'link', None
    for name, rx in FAQ:
        if rx.search(t):
            return 'faq', name
    if QUESTION.search(t):
        return 'question', None
    if EXAM.search(t):
        return 'exam', None
    return 'generic', None


# ---------------------------------------------------------------- texts
T = {
 'dm_link': {
  'de': 'Hallo! 👋 Hier ist der Link zum B1 Prüfungstrainer:\n{url}\n\nModelltest 1 bis 3 sind kostenlos. Viel Erfolg bei deiner Prüfung! 🍀',
  'en': 'Hi! 👋 Here is the link to the B1 German Exam Trainer:\n{url}\n\nTests 1 to 3 are free. Good luck with your exam! 🍀',
  'tr': 'Merhaba! 👋 B1 Almanca sınav uygulamasının bağlantısı:\n{url}\n\nİlk 3 test ücretsiz. Sınavında bol şans! 🍀',
  'ar': 'مرحبًا! 👋 هذا رابط تطبيق التدريب على امتحان الألمانية B1:\n{url}\n\nالاختبارات 1 إلى 3 مجانية. بالتوفيق في امتحانك! 🍀',
  'uk': 'Привіт! 👋 Ось посилання на застосунок для підготовки до іспиту з німецької B1:\n{url}\n\nТести 1–3 безкоштовні. Успіхів на іспиті! 🍀',
  'ru': 'Привет! 👋 Вот ссылка на приложение для подготовки к экзамену по немецкому B1:\n{url}\n\nТесты 1–3 бесплатны. Удачи на экзамене! 🍀',
  'fa': 'سلام! 👋 این لینک برنامهٔ تمرین آزمون آلمانی B1 است:\n{url}\n\nآزمون‌های 1 تا 3 رایگان‌اند. در آزمون موفق باشید! 🍀',
  'ro': 'Salut! 👋 Iată linkul către aplicația de pregătire pentru examenul de germană B1:\n{url}\n\nTestele 1–3 sunt gratuite. Mult succes la examen! 🍀',
 },
 'sent': {  # public reply after a successful DM
  'de': ['📩 Ist unterwegs – schau in deine Nachrichten!', 'Gerne! Der Link ist in deinen DMs. 📩', 'Hab dir den Link geschickt! 📩'],
  'en': ['📩 Sent – check your messages!', 'Sure! The link is in your DMs. 📩', 'Just sent you the link! 📩'],
  'tr': ['📩 Gönderdik, mesajlarına bak!', 'Tabii! Bağlantı DM’de. 📩', 'Bağlantıyı mesajla gönderdik! 📩'],
  'ar': ['📩 أرسلنا لك الرابط، تفقّد رسائلك!', 'بكل سرور! الرابط في رسائلك الخاصة. 📩'],
  'uk': ['📩 Надіслали – перевірте повідомлення!', 'Звісно! Посилання вже в особистих. 📩'],
  'ru': ['📩 Отправили – проверьте сообщения!', 'Конечно! Ссылка уже в личных сообщениях. 📩'],
  'fa': ['📩 فرستادیم، دایرکت‌تان را ببینید!', 'حتماً! لینک در دایرکت است. 📩'],
  'ro': ['📩 Trimis – verifică mesajele!', 'Sigur! Linkul e în mesaje private. 📩'],
 },
 'bio': {  # public reply when no DM could be sent
  'de': 'Danke! 🔗 Den Link findest du in unserer Bio. In Google Play: „Deutsch B1 Prüfung: Modelltest“.',
  'en': 'Thanks! 🔗 The link is in our bio. On Google Play: “German B1 Exam: Practice Tests”.',
  'tr': 'Teşekkürler! 🔗 Bağlantı profilimizde. Google Play’de: “Almanca B1 Sınav Hazırlık”.',
  'ar': 'شكرًا! 🔗 الرابط في ملفنا الشخصي. على Google Play: «امتحان الألمانية B1: اختبارات».',
  'uk': 'Дякуємо! 🔗 Посилання в нашому профілі. У Google Play: «Німецька B1: тести до іспиту».',
  'ru': 'Спасибо! 🔗 Ссылка в нашем профиле. В Google Play: «Немецкий B1: тесты к экзамену».',
  'fa': 'ممنون! 🔗 لینک در بیوی ماست. در Google Play: «آزمون آلمانی B1: تمرین امتحان».',
  'ro': 'Mulțumim! 🔗 Linkul e în bio. În Google Play: „Examen germană B1: teste”.',
 },
 'thanks': {
  'de': ['Danke dir! 🙌', 'Vielen Dank! Viel Erfolg beim Lernen 🍀', 'Danke! Du schaffst das 💪', 'Freut uns sehr! 😊'],
  'en': ['Thank you! 🙌', 'Thanks a lot! Good luck with your studies 🍀', 'Thanks! You’ve got this 💪'],
  'tr': ['Teşekkürler! 🙌', 'Çok teşekkür ederiz! Çalışmalarında bol şans 🍀', 'Sağ ol! Başaracaksın 💪'],
  'ar': ['شكرًا لك! 🙌', 'شكرًا جزيلًا! بالتوفيق في دراستك 🍀', 'شكرًا! أنت قادر على النجاح 💪'],
  'uk': ['Дякуємо! 🙌', 'Щиро дякуємо! Успіхів у навчанні 🍀', 'Дякуємо! У вас усе вийде 💪'],
  'ru': ['Спасибо! 🙌', 'Большое спасибо! Удачи в учёбе 🍀', 'Спасибо! У вас всё получится 💪'],
  'fa': ['ممنون! 🙌', 'خیلی ممنون! در یادگیری موفق باشید 🍀', 'ممنون! شما می‌توانید 💪'],
  'ro': ['Mulțumim! 🙌', 'Mulțumim mult! Spor la învățat 🍀', 'Mersi! Poți reuși 💪'],
 },
 'luck': {
  'de': ['Viel Erfolg bei deiner Prüfung! 🍀 Du schaffst das.', 'Wir drücken dir die Daumen! 🍀'],
  'en': ['Good luck with your exam! 🍀 You’ve got this.', 'Fingers crossed for you! 🍀'],
  'tr': ['Sınavında bol şans! 🍀 Başaracaksın.', 'Başarılar dileriz! 🍀'],
  'ar': ['بالتوفيق في امتحانك! 🍀 أنت قادر على ذلك.', 'نتمنى لك النجاح! 🍀'],
  'uk': ['Успіхів на іспиті! 🍀 У вас усе вийде.', 'Тримаємо за вас кулаки! 🍀'],
  'ru': ['Удачи на экзамене! 🍀 У вас всё получится.', 'Держим за вас кулачки! 🍀'],
  'fa': ['در آزمون موفق باشید! 🍀 شما می‌توانید.', 'برایتان آرزوی موفقیت داریم! 🍀'],
  'ro': ['Mult succes la examen! 🍀 Poți reuși.', 'Îți ținem pumnii! 🍀'],
 },
 'faq_price': {
  'de': 'Modelltest 1 bis 3 sind kostenlos. Alle 30 Tests schaltest du mit einem Einmalkauf frei, ohne Abo. Den aktuellen Preis siehst du in Google Play.',
  'en': 'Tests 1 to 3 are free. You unlock all 30 tests with a one-time purchase, no subscription. Google Play shows the current price.',
  'tr': 'İlk 3 test ücretsiz. 30 testin hepsini tek seferlik bir satın alımla açarsın, abonelik yok. Güncel fiyatı Google Play’de görebilirsin.',
  'ar': 'الاختبارات 1 إلى 3 مجانية. تفتح الاختبارات الثلاثين كلها بعملية شراء واحدة دون اشتراك. السعر الحالي يظهر في Google Play.',
  'uk': 'Тести 1–3 безкоштовні. Усі 30 тестів відкриваються однією покупкою, без підписки. Актуальну ціну показує Google Play.',
  'ru': 'Тесты 1–3 бесплатны. Все 30 тестов открываются одной покупкой, без подписки. Актуальную цену показывает Google Play.',
  'fa': 'آزمون‌های 1 تا 3 رایگان‌اند. همهٔ 30 آزمون با یک بار خرید باز می‌شوند، بدون اشتراک. قیمت فعلی را در Google Play می‌بینید.',
  'ro': 'Testele 1–3 sunt gratuite. Toate cele 30 de teste se deblochează cu o singură plată, fără abonament. Prețul actual îl vezi în Google Play.',
 },
 'faq_ios': {
  'de': 'Die App gibt es im Moment nur für Android (Google Play). Danke für dein Interesse! 🙏',
  'en': 'The app is only on Android (Google Play) for now. Thanks for your interest! 🙏',
  'tr': 'Uygulama şimdilik sadece Android’de (Google Play) var. İlgin için teşekkürler! 🙏',
  'ar': 'التطبيق متاح حاليًا على Android فقط (Google Play). شكرًا لاهتمامك! 🙏',
  'uk': 'Поки що застосунок є лише для Android (Google Play). Дякуємо за інтерес! 🙏',
  'ru': 'Пока приложение есть только для Android (Google Play). Спасибо за интерес! 🙏',
  'fa': 'این برنامه فعلاً فقط برای Android (Google Play) است. ممنون از توجه شما! 🙏',
  'ro': 'Deocamdată aplicația există doar pentru Android (Google Play). Mulțumim pentru interes! 🙏',
 },
 'faq_official': {
  'de': 'Die App ist ein unabhängiges Übungsangebot und nicht mit der telc gGmbH verbunden. Die 30 Modelltests folgen dem Format der schriftlichen Prüfung telc Deutsch B1.',
  'en': 'The app is an independent practice tool, not affiliated with telc gGmbH. The 30 mock tests follow the format of the written telc Deutsch B1 exam.',
  'tr': 'Uygulama bağımsız bir alıştırma aracıdır, telc gGmbH ile bağlantısı yoktur. 30 deneme sınavı, yazılı telc Deutsch B1 sınavının formatındadır.',
  'ar': 'التطبيق أداة تدريب مستقلة لا ترتبط بشركة telc gGmbH. الامتحانات التجريبية الثلاثون مكتوبة بصيغة الامتحان الكتابي telc Deutsch B1.',
  'uk': 'Це незалежний застосунок для підготовки, не пов’язаний із telc gGmbH. 30 пробних іспитів відповідають формату письмового іспиту telc Deutsch B1.',
  'ru': 'Это независимое приложение для подготовки, не связанное с telc gGmbH. 30 пробных экзаменов соответствуют формату письменного экзамена telc Deutsch B1.',
  'fa': 'این برنامه یک ابزار تمرینی مستقل است و ارتباطی با شرکت telc gGmbH ندارد. 30 آزمون آزمایشی در قالب آزمون کتبی telc Deutsch B1 نوشته شده‌اند.',
  'ro': 'Aplicația este un instrument independent de exersare, fără legătură cu telc gGmbH. Cele 30 de teste urmează formatul examenului scris telc Deutsch B1.',
 },
 'faq_oral': {
  'de': 'Die App trainiert die schriftliche Prüfung: Lesen, Sprachbausteine, Hören und Schreiben. Die mündliche Prüfung ist nicht enthalten.',
  'en': 'The app trains the written exam: reading, language elements, listening and writing. The oral exam is not included.',
  'tr': 'Uygulama yazılı sınavı çalıştırır: okuma, dil yapıları, dinleme ve yazma. Sözlü sınav dahil değildir.',
  'ar': 'يدرّبك التطبيق على الامتحان الكتابي: القراءة والعناصر اللغوية والاستماع والكتابة. الامتحان الشفهي غير مشمول.',
  'uk': 'Застосунок тренує письмовий іспит: читання, мовні елементи, аудіювання й письмо. Усний іспит не входить.',
  'ru': 'Приложение тренирует письменный экзамен: чтение, языковые элементы, аудирование и письмо. Устный экзамен не входит.',
  'fa': 'این برنامه آزمون کتبی را تمرین می‌دهد: خواندن، اجزای زبانی، شنیدن و نوشتن. آزمون شفاهی شامل نیست.',
  'ro': 'Aplicația exersează examenul scris: citire, elemente de limbă, ascultare și scriere. Examenul oral nu este inclus.',
 },
 'faq_offline': {
  'de': 'Ja, die App funktioniert offline und ohne Konto.',
  'en': 'Yes, the app works offline and without an account.',
  'tr': 'Evet, uygulama çevrimdışı ve hesapsız çalışır.',
  'ar': 'نعم، يعمل التطبيق دون اتصال وبلا حساب.',
  'uk': 'Так, застосунок працює офлайн і без облікового запису.',
  'ru': 'Да, приложение работает офлайн и без аккаунта.',
  'fa': 'بله، برنامه آفلاین و بدون حساب کاربری کار می‌کند.',
  'ro': 'Da, aplicația funcționează offline și fără cont.',
 },
 'suffix_dm': {'de': ' Den Link hab ich dir per DM geschickt. 📩', 'en': ' I’ve sent you the link by DM. 📩',
               'tr': ' Bağlantıyı DM ile gönderdik. 📩', 'ar': ' أرسلنا لك الرابط في رسالة خاصة. 📩',
               'uk': ' Посилання надіслали в особисті. 📩', 'ru': ' Ссылку отправили в личные сообщения. 📩',
               'fa': ' لینک را در دایرکت فرستادیم. 📩', 'ro': ' Ți-am trimis linkul în mesaj privat. 📩'},
 'suffix_bio': {'de': ' Link in der Bio 🔗', 'en': ' Link in bio 🔗', 'tr': ' Bağlantı profilde 🔗', 'ar': ' الرابط في الملف الشخصي 🔗',
                'uk': ' Посилання в профілі 🔗', 'ru': ' Ссылка в профиле 🔗', 'fa': ' لینک در بیو 🔗', 'ro': ' Link în bio 🔗'},
}
# Quiz replies stay German: the quizzes are German practice.
QUIZ = {
 'right': ['Richtig! ✅ Sehr gut.', 'Genau! ✅ Gut gemacht.', 'Stimmt! ✅ Weiter so 💪', 'Richtig! ✅ Das sitzt.'],
 'wrong': ['Leider nicht ganz. Versuch’s noch einmal! 😉', 'Knapp daneben. Schau dir den Satz noch einmal an 😉',
           'Nicht ganz. Die Auflösung kommt bald! 😉'],
 'wrong_after': 'Leider nicht ganz. Richtig ist {letter}) {word}.',
}


def pick(key, lang, rng=random):
    v = T[key].get(lang) or T[key]['en']
    return rng.choice(v) if isinstance(v, list) else v


def check_texts():
    """Every text exists in every language (used by the tests)."""
    missing = [(k, l) for k, d in T.items() for l in LANGS if l not in d]
    return missing
