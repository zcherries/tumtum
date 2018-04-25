import dialogs
import pytumblr
import re
import secrets

from pprint import pformat, pprint
from typing import Any, Callable, Dict, List, Tuple
from urllib.parse import urlparse

from tumtum import (
    constants, helpers, submissions
)
from tumtum.super_post import SuperPost


class Post(SuperPost):
    is_reblog = False
    is_submission = False
    netloc = ''
    blog_name = ''
    post_id = 0

    def __init__(self, post_url: str=None) -> None:
        if post_url is not None:
            self.is_reblog = '#reblog' in post_url
            self.netloc = self.get_netloc(post_url)
            self.blog_name = self.get_post_blog()
            self.post_id = self.get_post_id_from_url(
                post_url,
            )

    def additional_text_html(
        self,
        additional_text: str,
    ) -> str:
        if additional_text:
            text = '. '.join(
                i.capitalize()
                for i in additional_text.split('. '))
            return f'<p>{text}</p>'
        return ''

    def fill_form(
        self,
        post: Dict[str, Any]=None,
    ) -> Dict[str, str]:
        info_list_value = ''
        url = ''
        url_text = ''

        if post:
            selections = self.get_form_info_list(post)
            url, url_text = self.get_form_url(selections)
            info_list_value = ','.join(selections)

        fields = [
            {
                'type': 'text',
                'title': '',
                'key': 'info_list',
                'value': info_list_value,
                'placeholder': 'Info list',
                'autocorrection': True,
                'autocapitalization': True,
            },
            {
                'type': 'text',
                'title': '',
                'key': 'additional_text',
                'value': '',
                'placeholder': 'Additional text',
                'autocorrection': True,
                'autocapitalization': False,
            },
            {
                'type': 'url',
                'title': '',
                'key': 'url',
                'value': url,
                'placeholder': 'Optional URL',
                'autocorrection': False,
                'autocapitalization': False,
            },
            {
                'type': 'text',
                'title': '',
                'key': 'url_text',
                'value': url_text,
                'placeholder': 'URL text',
                'autocorrection': True,
                'autocapitalization': False,
            },
        ]

        if post and self.is_reblog:
            should_keep_tree = self.should_keep_tree(post)
            if should_keep_tree:
                fields.append({
                    'type': 'switch',
                    'title': 'Keep reblog tree',
                    'key': 'keep_tree',
                    'value': should_keep_tree,
                })

        return dialogs.form_dialog(
            title='Questions',
            fields=fields,
        ) or {}

    def get_client(self):
        return pytumblr.TumblrRestClient(
            constants.TUMBLR_CONSUMER_KEY,
            constants.TUMBLR_CONSUMER_SECRET,
            constants.OAUTH_TOKEN,
            constants.OAUTH_SECRET,
        )

    def get_download_and_post_data(self) -> Dict[str, Any]:
        post = self.get_post_from_post_id()
        post_type = post.get('type', 'photo')

        media = self.get_media_from_post(post, post_type)
        if post:
            self.like_post(post)

        form = self.fill_form(post)
        info_list = form.get('info_list', '')
        if info_list:
            info_list = helpers.split_list(info_list)
            form['info_list'] = info_list

        tags = self.make_tags(info_list, post_type)

        blog_captions = []
        blogs = self.get_blogs(info_list, tags)
        for blog in blogs:
            blog_captions.append(
                self.make_caption(
                    blog,
                    form,
                )
            )

        folder = self.make_folder_name_from_info_list(info_list)
        if not folder and post:
            folder = self.get_folder_for_download(post, tags)

        return {
            'status': 'success',
            'type': post_type,
            'reblog_key': self.get_reblog_key(post),
            'post_id': post.get('id') if post else None,
            'keep_tree': form.get('keep_tree', False),
            'blog_captions': blog_captions,
            'tags': tags,
            'folder': folder,
            'media': media,
        }

    def get_download_data(self) -> Dict[str, Any]:
        post = self.get_post_from_post_id()
        if post:
            self.like_post(post)
            post_type = post.get('type')
            folder = self.get_folder_for_download(post)
            media = self.get_media_from_post(post, post_type)

            return {
                'status': 'success',
                'type': post_type,
                'post': post,
                'folder': folder,
                'media': media,
            }

        return {'status': 'Error'}

    def get_file_name(
        self,
        summary: str,
        number: str='',
    ) -> str:
        if summary:
            summary = re.sub(
                constants.LINES_RE,
                ' ',
                summary,
                re.IGNORECASE,
            )
            return f' - {summary}{number}'
        return f' {number}'

    def get_form_info_list(
        self,
        post: Dict[str, Any]
    ) -> List[str]:
        options = []
        tags = post.get('tags')
        post_author = self.get_post_author(post)
        if post_author:
            options = [f'{post_author}.tumblr.com']
        if tags:
            options += tags + [
                constants.FORM_BLANK, self.netloc
            ]
            for i, opt in enumerate(options):
                if 'tumblr' not in opt:
                    options[i] = opt.title()
            selections = dialogs.list_dialog(
                title='Select tags to use as names:',
                items=options,
                multiple=True,
            ) or []

            if constants.FORM_BLANK in selections:
                selections = []

            return selections
        elif self.is_reblog:
            return options or [self.netloc]
        return options

    def get_form_url(
        self,
        selections: List[str],
    ) -> Tuple[str, str]:
        links = [
            l for l in selections if (
                l != constants.FORM_BLANK
                and l != self.netloc
            )
        ]
        can_link = (
            self.is_reblog
            and links
            and not self.is_submission
        )
        if can_link:
            tag = dialogs.list_dialog(
                title='Which tag do you want to link?',
                items=links,
                multiple=False,
            ) or ''

            if tag:
                url = f'http://{self.netloc}/tagged/{tag}'
                url = re.sub(
                    constants.SPACES_RE,
                    '%20',
                    url,
                )

                url_text = (
                    f'This tag "<strong>{tag}</strong>" ' +
                    'is 🔥!&nbsp;&#8250;'
                )
                return url, url_text
        return ('', '')

    def get_media_from_post(
        self,
        post: Dict[str, Any]={},
        post_type: str='',
    ) -> List[Dict[str, str]]:
        summary = post.get('summary', '')

        media = []
        if post_type and post_type == 'photo':
            photos = post.get('photos', [])
            media = self.get_photos_info(
                photos, summary)
        elif post_type and post_type == 'video':
            media.append({
                'title': self.get_file_name(
                    summary),
                'url': post.get('video_url')
            })
        return media

    def get_netloc(self, url: str='') -> str:
        if url and self.is_tumblr_url(url):
            return urlparse(url).netloc
        return ''

    def get_photos_info(
        self,
        photos: List[Dict[str, Any]],
        summary: str,
    ) -> List[Dict[str, str]]:
        num_photos = len(photos)
        media = []
        for idx, photo in enumerate(photos):
            caption = photo.get('caption', '') or summary
            photo_num = ''
            if num_photos > 1:
                photo_num = f' {idx + 1}'
            photo_url = photo.get(
                'original_size', {}).get('url', '')
            media.append({
                'title': self.get_file_name(
                    caption, photo_num),
                'url': photo_url,
            })

        return media

    def get_post_author(self, post: Dict[str, Any]) -> str:
        if post and self.is_submission:
            return post.get('post_author', '')
        return ''

    def get_post_blog(self, url: str='') -> str:
        if self.netloc:
            return self.netloc.split('.')[0]
        return ''

    def get_post_from_post_id(self) -> Dict[str, Any]:
        if self.post_id:
            client = self.get_client()
            response = client.posts(
                self.blog_name,
                id=self.post_id,
            )
            status = (
                response
                .get('meta', {})
                .get('status', 200)
            )
            if status != 200:
                dialogs.alert(
                    title='Error',
                    message=pformat(response),
                )

            posts = response.get('posts')
            if posts:
                post = posts[0]
                self.is_submission = post.get(
                    'is_submission', False)
                return post
        return {}

    def get_post_id_from_url(self, url: str) -> int:
        if url and self.is_tumblr_url(url):
            return int(
                urlparse(url).path.split('/')[2])
        return 0

    @staticmethod
    def get_reblog_key(post: Dict[str, str]) -> str:
        if post:
            return post.get('reblog_key')

    @staticmethod
    def has_bottom(line: str) -> bool:
        return re.match(
            constants.BOTTOM_RE,
            line,
            re.IGNORECASE,
        )

    @staticmethod
    def has_makeup(line: str) -> bool:
        return re.match(
            constants.MAKEUP_RE,
            line,
            re.IGNORECASE,
        )

    @staticmethod
    def has_photographer(line: str) -> bool:
        return re.match(
            constants.PHOTOGRAPHER_RE,
            line,
            re.IGNORECASE,
        )

    @staticmethod
    def has_top(line: str) -> bool:
        return re.match(
            constants.TOP_RE,
            line,
            re.IGNORECASE,
        )

    @staticmethod
    def html_check_out_other_blog(
        sub_domain: str,
    ) -> str:
        other_blogs = [
            blog for blog in constants.BLOGS if blog != sub_domain]

        try_blog = secrets.choice(other_blogs)
        selection = """
        <a href="https://{0}.tumblr.com/">{0}</a>
        """.format(try_blog)

        return f'<small>🥇 My blogs are lit! Check out: {selection} 🥇</small>'

    def html_footer(
        self,
        sub_domain: str,
    ) -> str:
        return """
        <small>
            <p>
                {divider}
            </p>
            <p>
                {followers}
                Follow&nbsp;
                <a href="https://{sub_domain}.tumblr.com">
                    {sub_domain}&nbsp;&#8250;
                </a>
                <br />
                {submit_phrase}&nbsp;
                <a href="https://{sub_domain}.tumblr.com/submit">
                    Submit to {sub_domain}&nbsp;&#8250;
                </a>
            </p>
            {other_blog}
        </small>
        """.format(
            divider=constants.DIVIDERS[sub_domain],
            followers=self.get_followers(sub_domain),
            sub_domain=sub_domain,
            submit_phrase=self.submit_phrase(sub_domain),
            other_blog=self.html_check_out_other_blog(sub_domain),
        )

    def html_name(
        self,
        blog: str,
        name: str,
    ) -> str:
        if '<a href="https' in name:
            return name
        prefix = ''

        if self.has_bottom(name):
            prefix = constants.BOTTOM
            name = re.sub(
                constants.BOTTOM_RE,
                '',
                name,
                re.IGNORECASE,
            )

        if self.has_makeup(name):
            prefix = constants.MAKEUP
            name = re.sub(
                constants.MAKEUP_RE,
                '',
                name,
                re.IGNORECASE,
            )

        if self.has_photographer(name):
            prefix = constants.PHOTOGRAPHER
            name = re.sub(
                constants.PHOTOGRAPHER_RE,
                '',
                name,
                re.IGNORECASE,
            )

        if self.has_top(name):
            prefix = constants.TOP
            name = re.sub(
                constants.TOP_RE,
                '',
                name,
                re.IGNORECASE,
            )

        name = name.title()

        return """
            {prefix}<strong>{name}</strong>{more}<br />
        """.format(
            prefix=prefix,
            name=name,
            more=self.html_more_of_him(
                re.sub(
                    constants.NAME_SUBS_RE,
                    '',
                    name,
                    re.IGNORECASE,
                ),
                blog,
            )
        )

    def html_names(
        self,
        blog: str,
        info_list: List[str],
    ) -> str:
        names_list = self.make_name_list(info_list)
        names = '<strong>Who is this? Comment if you know.</strong>'
        if self.is_reblog:
            names = ''
        if names_list:
            names = ''
            for name in names_list:
                names += self.html_name(blog, name)
        return names

    @staticmethod
    def html_social_link(
        line: str,
        reg_ex: str,
        substitution: str,
    ) -> str:
        indicator = (
            f'His {constants.SITE_INDICATOR[reg_ex]}:&nbsp;'
        )
        url = re.sub(
            reg_ex,
            substitution,
            line,
            re.IGNORECASE,
        )
        text = re.sub(reg_ex, '', line, re.IGNORECASE)
        return '''
        <span>
            {0}
            <strong>
                <a href="https://{1}">{2}</a>
            </strong>
        </span><br />
        '''.format(
            indicator, url, text)

    def html_url(self, form: Dict[str, str]) -> str:
        url = form.get('url', '')
        url_text = form.get('url_text', '')
        if url and url_text:
            return f'<p><a href="{url}">{url_text}</a></p>'
        return ''

    def is_tumblr_url(self, url: str) -> bool:
        return 'tumblr' in url

    def like_post(self, post: Dict[str, str]) -> None:
        reblog_key = self.get_reblog_key(post)
        self.get_client().like(
            self.post_id, reblog_key)

    def make_caption(
        self,
        blog: str,
        form: Dict[str, Any],
    ) -> Dict[str, str]:
        info_list = form.get('info_list', '')
        names = self.html_names(blog, info_list)
        additional_text = self.additional_text_html(
            form.get('additional_text', ''),
        )
        url = self.html_url(form)
        footer = self.html_footer(blog)
        caption = names + additional_text + url + footer

        # Remove lines and spaces
        caption = re.sub(
            constants.LINES_SPACES_RE,
            '',
            caption,
            re.IGNORECASE,
        )

        return {
            'blog': blog,
            'caption': caption
        }

    def make_folder_name_from_info_list(
        self,
        info_list: List[str],
    ) -> str:
        new_list = []
        for line in info_list:
            if line:
                line = self.process_social(
                    line,
                    constants.NAME_SUBS,
                    self.social_media_name,
                )

                if self.has_bottom(line):
                    line = re.sub(
                        constants.BOTTOM_RE,
                        '',
                        line,
                        re.IGNORECASE,
                    )

                if self.has_makeup(line):
                    line = re.sub(
                        constants.MAKEUP_RE,
                        'makeup by ',
                        line,
                        re.IGNORECASE,
                    )

                if self.has_photographer(line):
                    line = re.sub(
                        constants.PHOTOGRAPHER_RE,
                        'by ',
                        line,
                        re.IGNORECASE,
                    )

                if self.has_top(line):
                    line = re.sub(
                        constants.TOP_RE,
                        '',
                        line,
                        re.IGNORECASE,
                    )
                line = re.sub(
                    constants.SITE_RE,
                    '',
                    line,
                    re.IGNORECASE,
                )
                new_list.append(line.title())

        new_list = filter(None, new_list)
        return ' | '.join(new_list)

    def make_name_list(
        self,
        info_list: List[str],
    ) -> List[str]:
        new_list = []
        for line in info_list:
            if line:
                line = self.process_social(
                    line,
                    constants.SITE_SUBS,
                    self.html_social_link,
                )

                new_list.append(line)
        return new_list

    @staticmethod
    def make_tags(
        info_list: str,
        post_type: str,
    ) -> str:
        # info_list tags
        tags = []
        for line in info_list:
            new_line = re.sub(
                constants.TAGS_RE,
                '',
                line.lower(),
                re.IGNORECASE,
            )
            if new_line not in tags:
                tags.append(new_line)

        # post_type tag
        tags.append(post_type)

        # extra tags
        extra_tag_objs = dialogs.list_dialog(
            title='Tag Selector',
            items=constants.TAG_CHOICES,
            multiple=True,
        ) or []
        extra_tags = [tag['title'] for tag in extra_tag_objs]
        extra_tags_str = ','.join(extra_tags)
        extra_tags = helpers.split_list(extra_tags_str)
        tags.extend(extra_tags)

        # Make sure only 30 tags
        num_tags = len(tags)
        while num_tags > 30:
            tags = dialogs.edit_list_dialog(
                title=f'Delete {str(num_tags - 30)} tags',
                items=tags,
                delete=True,
            )
            num_tags = len(tags)

        return ','.join(tags)

    def post_images(
        self,
        images: List[str],
    ) -> Dict[str, Any]:
        if not images:
            dialogs.alert(title='No images input')

        client = self.get_client()

        post_info = self.get_download_and_post_data()
        blog_captions = post_info.get('blog_captions')
        for caption in blog_captions:
            tags = helpers.split_list(post_info.get('tags'))

            response = client.create_photo(
                caption.get('blog', ''),
                caption=caption.get('caption', ''),
                tags=tags,
                data=images,
                photoset_layout='1'[:1] * len(images),
                state='queue',
            )
        return response

    def post_reblog(self) -> Dict[str, Any]:
        client = self.get_client()
        post_info = self.get_download_and_post_data()
        blog_captions = post_info.get('blog_captions')
        blogs = [
            caption['blog'] for caption in blog_captions
        ]

        for caption in blog_captions:
            tags = helpers.split_list(post_info.get('tags'))
            random_state = secrets.choice(
                constants.POST_STATES)
            blog = caption.get('blog')

            response = client.reblog(
                blog,
                id=post_info.get('post_id'),
                reblog_key=post_info.get('reblog_key'),
                comment=caption.get('caption'),
                tags=tags,
                attach_reblog_tree=post_info.get(
                    'keep_tree'),
                state=random_state,
            )
            if not response.get('id'):
                dialogs.alert(
                    title='Error',
                    message=pformat(response)
                )

        print(
            f'Reblogged to {len(blogs)} blog(s):',
            pformat(blogs),
        )
        return post_info

    def post_reblog_original(self) -> None:
        client = self.get_client()
        post = self.get_post_from_post_id()
        tags = post.get('tags')
        reblog_key = self.get_reblog_key(post)
        comment = dialogs.text_dialog(
            title='Enter comment:',
        )
        state = dialogs.list_dialog(
            title='Reblog state:',
            items=constants.POST_STATES,
        )

        for blog in constants.BLOGS:
            response = client.reblog(
                blog,
                id=self.post_id,
                reblog_key=reblog_key,
                comment=comment,
                tags=tags,
                state=state,
            )
            if not response.get('id'):
                dialogs.alert(
                    title='Error',
                    message=pformat(response)
                )

        print(
            'Reblogged to all blogs:',
            pformat(constants.BLOGS),
        )

    def post_submission(self) -> None:
        client = self.get_client()
        blog = dialogs.list_dialog(
            title='Submissions from which blog?',
            items=constants.BLOGS,
            multiple=False,
        )
        submissions = client.submission(blog)
        dialogs.text_dialog(
            title='',
            text=pformat(submissions)
        )

    def post_submission_request(self, blog: str) -> None:
        client = self.get_client()
        response = client.create_text(
            blog,
            title=submissions.REQUEST_TITLE,
            body=submissions.REQUEST_BODY,
            slug='submission-guidelines',
            format='html',
            state='queue',
            tags=[]
        )
        pprint(response)
        dialogs.hud_alert(
            message=f'Submissions requested: {blog}',
            icon='success',
            duration=2,
        )

    @staticmethod
    def process_social(
        line: str,
        sub_obj: Dict[str, str],
        callback: Callable[[str, str, str], str],
    ) -> str:
        for reg_ex in constants.SOCIAL_MEDIA_RE_LIST:
            if re.search(reg_ex, line, re.IGNORECASE):
                return callback(
                    line,
                    reg_ex,
                    sub_obj[reg_ex],
                )

        return line

    def should_keep_tree(self, post: Dict[str, str]) -> bool:
        if post and self.is_reblog:
            trail = post.get('trail', [])
            if len(trail) < 3 and len(trail) > 0:
                is_same_name = (
                    trail[0]
                    .get('blog')
                    .get('name')
                    == post.get('blog_name')
                )
                if is_same_name:
                    return True
        return False

    @staticmethod
    def social_media_name(
        line: str,
        reg_ex: str,
        symbol: str,
    ) -> str:
        re_line = re.sub(reg_ex, '', line, re.IGNORECASE)
        if symbol:
            return f'{re_line} - {symbol}'
        return re_line

    @staticmethod
    def submit_phrase(
        sub_domain: str,
    ) -> str:
        return constants.SUBMIT_PHRASES[sub_domain].format(
            sub_domain=sub_domain
        )
