# Demo Shop — seeded bugs (answer key, not served to the browser)

Serve with: `python3 -m http.server 4000 --directory eval-app/site` (done by `scripts/dev.sh`).
Test login: `demo@shop.test` / `demo123`.

| # | Page | Bug |
| --- | --- | --- |
| 1 | login.html | Any password with 3+ characters logs in `demo@shop.test` |
| 2 | signup.html | Empty name accepted; email only checked for a dot (no `@`) |
| 3 | shop.html | Total is wrong when quantity is 10 or more |
| 4 | contact.html | Empty message is accepted and reported as sent |
| 5 | index.html | Search with non-ASCII text (e.g. "Café") throws a console error and shows nothing |
| 6 | all pages | "Log out" link does nothing after logging in |
