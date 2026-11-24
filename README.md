# Instagram for B1 Prüfungstrainer

256 ready-made posts, enough until the end of March 2027 without a repeat: 104 regular posts (64 of them quizzes) and 152 daily tips, and a bot that publishes them at random times, answers comments and sends
the Play Store link. It uses only Instagram's official API, so the account is not at risk the way
it would be with a login-scraping tool.

```
content/posts.json      the 256 posts: caption, alt text, quiz answer, design text, seasonal window
out/*.jpg               the images, 1080 × 1350 (Instagram 4:5), plus contact_sheet.jpg
design/render.py        renders the images again after you change posts.json
bot/ig_bot.py           the bot (Python standard library only)
bot/replies.py          how comments are understood, and every reply text in 8 languages
bot/config.json         posting times, limits, image address
.github/workflows/      runs the bot every hour on GitHub Actions (free)
tests/                  python3 -m unittest discover -s tests
```

## What the bot does

**Regular posts.** Each week it picks 4 or 5 random posting times inside three windows that suit the
audience (07:30–09:00, 12:00–13:30, 18:00–21:30, Berlin time), at least 20 hours apart. The times
are different every week but the same in every hourly run. Run `python3 bot/ig_bot.py plan` to
see them. The first post is the German introduction. After that it picks posts at random, never
the same kind twice in a row (quizzes, which are more than half, at most twice in a row) and never
two non-German posts in a row. When all 92 regular posts have been shown it starts a new round, and repeats a post
only if it was last shown at least 60 days earlier. One round lasts about 20 weeks.

**Tipp des Tages.** Every day one tip, at a random time between 06:45–08:15 or 16:30–18:00, at least
three hours away from a regular post that day. The 143 regular tips go out in their order (grammar,
vocabulary, exam, writing, phrases and everyday life in Germany take turns) and then start again.

**Seasonal posts.** 12 posts and 9 tips have a date window (Nikolaus, Advent, Christmas, New Year,
winter, carnival, Valentine's Day, spring, the clock change, Easter). Inside its window a seasonal post
goes before the others; outside it is never posted. Windows written as `MM-DD` come back every year;
windows with a full date (carnival, clock change, Easter 2027, "Frohes neues Jahr 2027") happen once,
because these dates move. Update them for 2028.

**Quiz answers.** Two days after a quiz post it comments with the answer and a short explanation.

**Comments**, checked every hour on the 12 newest posts:

| Comment | Answer |
|---|---|
| asks for the link: “LINK”, “Link bitte”, “linki atar mısın”, “ссылку”, “لینک” … | Private message with the Play Store link in the commenter's language, plus a public reply “sent, check your messages”. |
| a quiz answer: “b”, “b) Deshalb”, “deshalb” | “Richtig!” or “Nicht ganz” (the answer itself only after the reveal) |
| price, iPhone, “is this official?”, oral exam, offline | A short factual answer in the commenter's language; plus the link by private message (not for iPhone). |
| “my exam is tomorrow”, “sınavım var” | “Good luck, you've got this! 🍀” |
| praise, thanks, emojis, tagged friends | A short thank-you, varied |
| spam (links, “promote it”, crypto …) | nothing |
| complaints (“Abzocke”, “scam”) and other open questions | **nothing automatic.** Listed under “NEEDS YOU” in the run log and in `status`, for you to answer yourself |

The language is guessed from the comment (8 languages), otherwise the post's language is used.

Instagram's rules that the bot follows:
- a private reply is allowed only once per comment and only within 7 days;
- one link per person per 30 days;
- at most 80 private messages a day and 25 replies per run.

The Play Store link carries `hl=<language>` so the store opens in the commenter's language. It also carries
`utm_source=instagram&utm_campaign=<post id>`, so in Play Console (Statistics → acquisition) you
can see which post brought installs.

**Limits it respects.**
- Instagram's publishing limit: the bot asks `content_publishing_limit` before every post.
- At most 5 hashtags (Instagram's limit since December 2025).
- Captions of at most 2,200 characters.
- Image posts must be JPEG.
- Every post that names telc carries the "not affiliated" line.

## Setting it up (about 30 minutes)

1. **Instagram account.** Create a new account for the app, for example `b1.pruefungstrainer`, and
   switch it to a professional account (Settings → Account type and tools → Switch to professional
   account → Creator or Business, category “Education”). No Facebook page is needed.

   Bio suggestion (123 of Instagram's 150 characters):
   ```
   Deutsch B1 Prüfung üben 🇩🇪
   30 Modelltests: Lesen · Hören · Schreiben
   Anweisungen in 8 Sprachen 🌍
   👇 Modelltest 1–3 kostenlos
   ```
   Profile link: `https://play.google.com/store/apps/details?id=com.seus.b1trainer&referrer=utm_source%3Dinstagram%26utm_medium%3Dbio`.
   Use the app icon (design/assets/icon.png) as the profile picture.

2. **Images online.** Instagram fetches each image from a public web address. Copy `out/*.jpg`
   (not `contact_sheet.jpg`) to your website folder `social/b1trainer/`. The developer-website zip
   already contains them. After uploading, check them:
   `python3 bot/ig_bot.py check`. Every post must show as reachable. If your domain is not seus.app,
   change `image_base_url` in `bot/config.json`.

3. **Meta app.** On developers.facebook.com → My Apps → Create app → use case “Manage messaging and
   content on Instagram”. Since late October 2026, new apps get **API setup with Unified login**; older
   apps may still show **API setup with Instagram login**. The bot works with both and picks the right
   address from the token.
   - **Unified login (new apps):** the app must belong to a business portfolio (business.facebook.com),
     and your Instagram professional account must be in the same portfolio. In Use cases → Instagram API →
     API setup with Unified login, add the permissions `instagram_basic`, `instagram_content_publish`,
     `instagram_manage_comments` and `instagram_manage_messages`. Then create a configuration with a
     **system-user access token** that never expires, and connect your Instagram account.
   - **Instagram login (older apps):** under “Generate access tokens”, add your account (accept the tester
     invite on instagram.com → Settings → Apps and websites) and use the four `instagram_business_*` permissions.
   - Either way the app can stay in development mode: an app that only serves your own account needs no App Review.

4. **Token and user ID.**
   - Unified login: the token starts with `EAA`, works on graph.facebook.com and does not expire.
   - Instagram login: the token starts with `IG`, works on graph.instagram.com and lasts 60 days.
   To find `IG_USER_ID`, run the workflow with command `whoami` (or locally:
   `IG_ACCESS_TOKEN=... python3 bot/ig_bot.py whoami`). It prints the kind of token and the Instagram
   account ID it can use. “Cannot parse access token” means the token is incomplete or has spaces in it.

5. **GitHub repository.** Create a **private** repository and upload this folder. It must be private,
   because `state/state.json` holds commenter usernames.
   Under Settings → Secrets and variables → Actions, add:
   - Secret `IG_ACCESS_TOKEN`: the token from step 4
   - Secret `IG_USER_ID`: the user ID
   - Secret `SCHEDULE_SALT`: any long random text (it seeds the random times)
   - Variable `IG_USERNAME`: the account name without @ (so the bot never answers itself)

6. **Token renewal (only for Instagram-login tokens).** Unified-login tokens never expire, so skip this step. The bot renews an `IG…` token once a week. To let it save the new
   token, create a fine-grained personal access token (GitHub → Settings → Developer settings) for
   this repository with permission “Secrets: Read and write”, and store it as secret `GH_PAT`.
   Without it, the run shows a warning, and you must replace `IG_ACCESS_TOKEN` by hand every 60 days.

7. **Test.** Actions → instagram → Run workflow:
   - command `check` → all images reachable;
   - command `comments` with dry run → shows what it would answer, changes nothing;
   - command `publish`, post `de-01-intro` → your first post goes out now.

   From then on the hourly schedule runs by itself. In a private repository each run uses about one
   minute of the 2,000 free Actions minutes a month; hourly runs need about 750.

Prefer your own computer? `cp .env.example .env`, fill it in, and run
`python3 bot/ig_bot.py run --env-file .env` hourly with cron. The computer must be on at the posting times.

## Before you rely on the private messages

Meta notes that some features “may not work properly” with Standard Access. Messages to people who have no role on
your app are the most likely to be affected. The bot is built for that case: if Instagram refuses the private message, the bot
answers publicly with “Link in the bio, or search Google Play for ‘Deutsch B1 Prüfung: Modelltest’”,
and the log shows `dm-failed`. Test it once with a second Instagram account: comment “LINK” on
a post and see whether the message arrives. If it does not, App Review for
`instagram_business_manage_messages` (with business verification) unlocks it. Until then, the bio
link carries the traffic.

## Changing posts

Edit `content/posts.json` (caption, `design` texts), then `python3 design/render.py` renders the
images again, and `python3 -m unittest discover -s tests` checks limits and images. Upload the new
images before the bot posts them. To add a post, copy an entry with the same template (`hero`,
`quiz`, `tips`, `table`, `big`, `languages`) and give it a new `id` and `image`.

Reply texts live in `bot/replies.py`. Quiz replies stay German on purpose, because the quizzes are German practice.

Useful commands:
```
python3 bot/ig_bot.py plan          # posting times this week and next, and the tip times
python3 bot/ig_bot.py status        # what was posted, token expiry, comments that need you
python3 bot/ig_bot.py publish --post de-11-free      # post one now
```

The two Arabic-script fonts in design/fonts (Noto Sans Arabic, Vazirmatn) are under the SIL Open
Font License; their license files are next to them.
