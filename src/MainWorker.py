from PyGoogleImgReverseSearch import GoogleImgReverseSearch
from strings import tr, en
from time import sleep
from logger import logger
import re
from CompareImageHashes import CompareImageHashes, HashedImage, ImgNotAvailable
from datetime import datetime
from collections import namedtuple
from rStuff import PostFetcher


class MainWorker:
    def __init__(self, bot, hashdb):
        self.good_bot_strs = ["good bot", "iyi bot", "güzel bot", "cici bot"]
        self.reddit_submission_regex = re.compile(
            r"^https?://(www.)*reddit.com/r/.+?/comments/(.+?)/.*"
        )

        self.hash_database = hashdb
        self.reverse_img_bot = bot
        self.fetcher = PostFetcher(
            bot=self.reverse_img_bot,
            stop_if_saved=True,
            subs=["KGBTR"],
            before_or_after="before",
            only_image=True,
            limit=7,
        )
        self.ReplyJob = namedtuple("ReplyJob", "reply_to text status")

    def comment_parser(self, body):
        sub_filter = None
        gallery_index = 0
        for n in body.split():
            n_len = len(n)
            if "sub:" in n and n_len >= 5:
                sub_filter = n[4:]
            elif "gallery:" in n and n_len >= 9:
                try:
                    gallery_index = int(n[8:]) - 1
                except ValueError:
                    pass
        return {"sub_filter": sub_filter, "gallery_index": gallery_index}

    def reply_builder(self, results, base_pic_url, link_mode):
        if {("out_of_pages", "out_of_pages")} == results:
            return ""
        image_hash_pairs = []
        already_appended_post_ids = set()
        hash_compare = CompareImageHashes(base_pic_url)
        for submission_url, submission_img_url in results:
            if submission_url == "out_of_pages":
                continue
            r_re = self.reddit_submission_regex.match(submission_url)
            if r_re is not None:
                post_id = r_re.group(2)
            else:
                continue
            post_info = self.reverse_img_bot.get_info_by_id("t3_" + post_id)
            if (
                post_info.id_ in already_appended_post_ids
                or post_info is None
                or not post_info.is_img
                or post_info.url.split("/")[-1] not in submission_img_url
            ):
                continue
            if post_info.is_gallery:
                img_url = post_info.gallery_media[0]
            else:
                img_url = post_info.url
            image_hash_pairs.append(
                (post_info, hash_compare.hamming_distance_percentage(img_url))
            )
            already_appended_post_ids.add(post_info.id_)

        post_hash_pair_sorted = [
            (post, hamming)
            for post, hamming in sorted(
                image_hash_pairs, key=lambda item: item[1], reverse=True
            )
        ][:6]
        final_txt = []
        for post, hamming in post_hash_pair_sorted:
            posted_at = datetime.fromtimestamp(post.created_utc).strftime("%d/%m/%Y")
            post_direct = f"https://{link_mode}.reddit.com{post.permalink}"
            sub = post.subreddit_name_prefixed
            post_title_truncated = post.title[:30]
            if len(post.title) > 30:
                post_title_truncated += "..."
            result_txt = f"- [{post_title_truncated}]({post_direct}) posted at {posted_at} in {sub} (%{hamming})"
            final_txt.append(result_txt)
        return "\r\n\n".join(final_txt)

    def search_loop(self, img_url, filter_site, link_mode):
        at_least_one_reply = False
        start_pg_index = 0
        reply_built = ""
        while not at_least_one_reply and start_pg_index != 15:
            logger.info(f"page {start_pg_index} to {start_pg_index + 3}")
            results = GoogleImgReverseSearch.reverse_search(
                pic_url=img_url,
                page_start=start_pg_index,
                page_end=start_pg_index + 3,
                filter_site=filter_site,
                skip_same_img_ref=True,
            )
            reply_built = self.reply_builder(results, img_url, link_mode)
            start_pg_index += 3
            at_least_one_reply = bool(reply_built)

            if ("out_of_pages", "out_of_pages") in results:
                break
        return reply_built

    def database_query_from_post(self, post):
        lang_f = tr if post.lang == "tr" else en
        try:
            hashfrompost = HashedImage(post.url, calculate_on_init=False)
        except ImgNotAvailable:
            reply_comment_text = f"{lang_f['nothing']}{lang_f['outro']}"
            return self.ReplyJob(post, reply_comment_text, "fail")
        result_txts = []
        for index in range(1):
            # if index == 0:
            #     query_results: list = self.hash_database.query(
            #         hashfrompost.get_phash(), "phash", 90, post.id_
            #     )
            # elif index == 1:
            #     query_results: list = self.hash_database.query(
            #         hashfrompost.get_dhash(), "dhash", 96, post.id_
            #     )
            # elif index == 2:
            #     query_result: list = self.hash_database.query(
            #         hashfrompost.get_ahash(), "ahash", 99, post.id_
            #     )
            # else:
            #     raise NotImplementedError
            query_results: list = self.hash_database.query(
                (hashfrompost.get_phash(), hashfrompost.get_dhash(), hashfrompost.get_ahash()), "", 90, post.id_
            )
            if query_results is not None:
                for query_result in query_results:
                    postid, similarity = query_result["post_id"], query_result["similarity"]
                    post_found = self.reverse_img_bot.get_info_by_id(postid)
                    link_mode = "np" if post.subreddit == "Turkey" else "www"
                    posted_at = datetime.fromtimestamp(post_found.created_utc).strftime(
                        "%d/%m/%Y"
                    )
                    post_direct = f"https://{link_mode}.reddit.com{post_found.permalink}"
                    sub = post_found.subreddit_name_prefixed
                    post_title_truncated = post_found.title[:30]
                    if len(post.title) > 30:
                        post_title_truncated += "..."
                    result_txts.append(f"- [{post_title_truncated}]({post_direct}) posted at {posted_at} in {sub} (%{similarity})")

        if bool(result_txts):
            result_txts_joined = '\r\n\n'.join(result_txts)
            reply_comment_text = (
                f"{lang_f['found_these']}\r\n\n{result_txts_joined}{lang_f['outro']}"
            )
            return self.ReplyJob(post, reply_comment_text, "success")
        else:
            reply_comment_text = f"{lang_f['nothing']}{lang_f['outro']}"
            return self.ReplyJob(post, reply_comment_text, "fail")

    def notif_handler2(self, notif):
        lang_f = tr if notif.lang == "tr" else en
        if notif.rtype == "username_mention":
            # NORMAL
            post = self.reverse_img_bot.get_info_by_id(notif.post_id)
            parsed_comment = self.comment_parser(notif.body)
            sub_filter, gallery_index = (
                parsed_comment["sub_filter"] or notif.subreddit,
                parsed_comment["gallery_index"],
            )

            if not post.is_img:
                reply_comment_text = f"{lang_f['no_image']}{lang_f['outro']}"
                return self.ReplyJob(notif, reply_comment_text, "fail")
            if post.is_gallery:
                img_url = post.gallery_media[gallery_index % len(post.gallery_media)]
            else:
                img_url = post.url
            filter_site = (
                f"www.reddit.com"
                if sub_filter.lower() == "all"
                else f"www.reddit.com/r/{sub_filter}"
            )
            logger.info(f"searching for: {img_url} in {filter_site}")

            link_mode = "np" if post.subreddit == "Turkey" else "www"
            reply_built = self.search_loop(img_url, filter_site, link_mode)

            if bool(reply_built):
                reply_comment_text = (
                    f"{lang_f['found_these']}\r\n\n{reply_built}{lang_f['outro']}"
                )
                return self.ReplyJob(notif, reply_comment_text, "success")
            else:
                reply_comment_text = f"{lang_f['nothing']}{lang_f['outro']}"
                return self.ReplyJob(notif, reply_comment_text, "fail")

        elif notif.rtype == "comment_reply":
            # GOOD BOT
            if any(x in notif.body.lower() for x in self.good_bot_strs):
                return self.ReplyJob(notif, lang_f["goodbot"], "success")

        else:
            return None

    def start_working(self):
        testing_post_o = self.reverse_img_bot.get_info_by_id("t3_m71m5p")
        while True:
            # AUTO POST FETCHING:
            # THUS, ONLY DATABASE QUERY DUE TO GOOGLE'S RATE LIMIT
            for post in self.fetcher.fetch_posts():
                logger.info(f"Checking: {post}")
                reply_job = self.database_query_from_post(post)
                tst_text = f"{reply_job.text}\r\n\npost:{post.id_}"
                if reply_job.status == "success":
                    self.reverse_img_bot.send_reply(
                        tst_text,  # reply_job.text,
                        testing_post_o,  # post,
                        handle_ratelimit=True
                    )
            # NOTIFS HANDLED HERE:
            # GOOGLE + DATABASE QUERY
            notifs = self.reverse_img_bot.check_inbox(rkind="t1")
            for notif in notifs:
                logger.info(notif)
                # GOOGLE
                self.reverse_img_bot.read_notifs([notif])
                reply_job = self.notif_handler2(notif)
                if reply_job is None:
                    continue
                if reply_job.status == "success":
                    self.reverse_img_bot.send_reply(
                        reply_job.text, notif, handle_ratelimit=True
                    )
                    continue

                # DATABASE
                post = self.reverse_img_bot.get_info_by_id(notif.post_id)
                reply_job_database = self.database_query_from_post(post)
                if reply_job_database.status == "success":
                    self.reverse_img_bot.send_reply(
                        reply_job_database.text, notif, handle_ratelimit=True
                    )
                    continue
                else:
                    self.reverse_img_bot.send_reply(
                        reply_job.text, notif, handle_ratelimit=True
                    )
                    continue

            sleep(5)
