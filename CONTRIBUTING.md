# How to contribute content

Feel free to reach out to Raf to propose new resources to share with the community.

* Linkedin: https://www.linkedin.com/in/rafael-roset-910b947/

# How to add new posts to this repository

The main branch of this repo is `gh-pages` as this website is hosted by [GitHub Pages][7].

[7]: https://pages.github.com/

## Build the website locally

This website uses [Jekyll][1], a static website generator, and runs entirely through [Docker Compose][5]. The only requirements are:

* [Docker][6] (with Compose)
* `make`

Once the repo is cloned, run `make serve` to start the Jekyll development server. The server generates content as you save it. Read the console output to find errors in your posts.

Visit the website at `http://localhost:8000/rafagas/`.

[4]: https://jekyllrb.com/docs/
[5]: https://docs.docker.com/compose/
[6]: https://docs.docker.com/get-docker/

## Create a new post

A new post needs to be added to a Markdown file with the following path and naming conventions:

* The file will be stored in the year folder inside `/_posts`.
* The name of the file will follow the `date-rid.md` pattern.

Posts use the following template:

```markdown
---
layout: rafaga
date: 
rid: 
rafagas:

- keyw: 
  desc: ''
  link: 

- keyw: 
  desc: ''
  link: 

- keyw: 
  desc: ''
  link: 

---
```

All the content is inside the frontmatter. To add custom text to a post, write it after the frontmatter.

The content of the frontmatter are:

* `date`: formatted using the [ISO 8601][2] standard, you can use either date or date & time (ex. `2020-11-25` or `2020-11-25T09:04:38+0100`)
* `rid`: is the number of the post, they are consecutive and independent of Raf's original postings
* `author`: Optional. If all the links come from another person, add this property. It changes the signature on the website and in the email.
* Then for each link:
  * `keyw`: the lowercase keyword that describes the link. The site converts it into a hashtag, so choose a single word. Always use lowercase.
  * `desc`: a simple sentence that describes the content. Usually this is a direct translation of Raf's description. You can adapt it for an English-speaking audience.
  * `link`: the link to share. If possible, do not use redirecting services.

Additionally, the following properties can be also added to any link:
  * `lang`: Optional. If the link content is not in English, add this property using the [ISO 639-1][3] language identifier (ex. `ES`, `DE`)
  * `via`: if someone else shared the link with Raf, add this property with the social network handle (include the `@` character). Always use single quotes.
  * `invalid: true`: a maintenance property. It shows that the link does not work anymore.
  * `nocheck: true`: a maintenance property. It tells the link checker to skip this link.

[1]: https://jekyllrb.com/
[2]: https://en.wikipedia.org/wiki/ISO_8601
[3]: https://en.wikipedia.org/wiki/ISO_639-1

## Optional: enrich your post

> NOTE: This step is optional. The website does not use the new information yet, so you can skip it.

The script `./script/microlink.py` sends each non-enriched link from the last 5 posts to the <https://microlink.io> API. The API returns a few details about each link. The script saves these details in a `microlink` property. The script then rewrites the frontmatter, so your content can look a bit different.

Run the script with `make microlink`. No local Python installation is needed because it runs inside Docker. It takes a few seconds to gather all the metadata. If you want to check that the website stays the same, keep the Jekyll server running.

```bash
$ make microlink
```

## Validate your post

A validator checks that posts follow the rules above. Run it before contributing:

```bash
$ make validate       # posts you added or changed compared to origin/gh-pages
$ make validate-all   # report on every post, it never fails
```

For each post, it checks the `date`, the `rid`, and the file name (`date-rid.md` in the year folder). It checks that no other post uses the same `rid` or `date`. It checks that the post has at least 1 link.

For each link, it checks these rules:

* `link` is a valid URL.
* `desc` is not empty.
* `keyw` is lowercase (letters, digits, and hyphens, no spaces).
* `lang` is a 2-letter uppercase ISO 639-1 code.
* `via` starts with `@`.
* `invalid` and `nocheck` are `true` or `false`.

It also warns about unknown keys. It also warns about links that were published in the last 180 days.

Older posts have legacy problems (multi-word keywords, lowercase `lang`...). Those are only reported as warnings, so maintenance changes on old posts are never blocked: a problem is an error only in new posts and in links that you add or edit.

The same check runs on pull requests to `gh-pages` once they are ready for review (draft PRs are skipped).

### Optional: run it as a git pre-commit hook

If you install [uv](https://docs.astral.sh/uv/), [pre-commit](https://pre-commit.com) can check each post when you commit it:

```bash
$ uv tool install pre-commit
$ pre-commit install
```

## Contribute your post

If you are a project maintainer, you can push your changes to the `gh-pages` branch of the main repository. If you are a contributor, create a Pull Request for the maintainers to review and approve.

## What happens after a new post is commited to the repository

There are two [Zapier][11] tasks that are tracking different RSS feeds from the website:

* One is tracking the [posts feed][8] to send an email to the Rafagas mailing list
* The other is tracking the [links feed][9] to schedule the new links to the Twitter account using [IFTTT][10]

[8]: https://geoinquiets.github.io/rafagas/atom.xml
[9]: https://geoinquiets.github.io/rafagas/atomic_atom.xml
[10]: https://ifttt.com/home
[11]: https://zapier.com/
