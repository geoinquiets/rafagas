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

Once the repo is cloned, run `make serve` to start the Jekyll development server. It will autogenerate content as it's stored but check the console output for errors in your posts.

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

All the content is inside the frontmatter, if you want to add some custom text to a post you can do that after the frontwmatter.

The content of the frontmatter are:

* `date`: formatted using the [ISO 8601][2] standard, you can use either date or date & time (ex. `2020-11-25` or `2020-11-25T09:04:38+0100`)
* `rid`: is the number of the post, they are consecutive and independent of Raf's original postings
* `author`: Optinal. Occasionally, Raf specifies that all the links are coming from another person, this property will change the signature in the website and email to reflect it.
* Then for each link:
  * `keyw`: the lowcase keyword to describe the link, it will be converted into a hashtag so better choosing a single word. All lowcase, no exceptions.
  * `desc`: a simple sentence describing the content, normally just a direct translation of Raf's description but you may want to adapt it to an English-speaking audience
  * `link`: the link to share, it's always better avoiding redirecting services, if possible

Additionally, the following properties can be also added to any link:
  * `lang`: Optional. If the link content is not in English, add this property using the [ISO 639-1][3] language identifier (ex. `ES`, `DE`)
  * `via`: if Raf is marking this link as shared by someone else, add this property with the social network handle (including the `@` character) and **always** use single quotes.
  * `invalid: true`: this is a maintenance property to indicate the link is not working anymore.
  * `nocheck: true`: this is a maintenance property to indicate to the link checker that this link should not be tested

[1]: https://jekyllrb.com/
[2]: https://en.wikipedia.org/wiki/ISO_8601
[3]: https://en.wikipedia.org/wiki/ISO_639-1

## Optional: enrich your post

> NOTE: This an optional step since the new information is still not used in the website so feel free to skip this one.

There is a script at `./script/microlink.py` that will send each non-enriched link from the last five posts to <https://microlink.io> API endpoint to gather a few details from the link itself. This new details are saved in a `microlink` property. After the file checking the frontmatter is rewritten so don't worry if you see your content a bit different.

Run the script with `make microlink`. No local Python installation is needed; it runs inside Docker. It will take a few seconds to gather all the metadata. You may want to have the Jekyll server running to see if the website remains the same after running the script.

```bash
$ make microlink
```

## Contribute your post

Depending if you are a project maitainer or a contributor you may push your changes to the `gh-pages` branch of the main repository or create a Pull Request for the maintainers to review and approve.

## What happens after a new post is commited to the repository

There are two [Zapier][11] tasks that are tracking different RSS feeds from the website:

* One is tracking the [posts feed][8] to send an email to the Rafagas mailing list
* The other is tracking the [links feed][9] to schedule the new links to the Twitter account using [IFTTT][10]

[8]: https://geoinquiets.github.io/rafagas/atom.xml
[9]: https://geoinquiets.github.io/rafagas/atomic_atom.xml
[10]: https://ifttt.com/home
[11]: https://zapier.com/
