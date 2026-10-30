const post = document.body.dataset.scrollPost;
if (post) document.getElementById('post-' + post)?.scrollIntoView();
