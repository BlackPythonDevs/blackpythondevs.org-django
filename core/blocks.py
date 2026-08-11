"""StreamField blocks used across page types."""

from wagtail import blocks
from wagtail.embeds.blocks import EmbedBlock
from wagtail.images.blocks import ImageBlock


class CalloutBlock(blocks.StructBlock):
    """A bordered aside — the gold left-border treatment from the old site."""

    heading = blocks.CharBlock(required=False)
    text = blocks.RichTextBlock()

    class Meta:
        icon = "warning"
        template = "core/blocks/callout.html"


class CardBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    text = blocks.RichTextBlock(required=False)
    link_url = blocks.CharBlock(required=False)
    link_text = blocks.CharBlock(required=False)

    class Meta:
        icon = "doc-empty"
        template = "core/blocks/card.html"


class CardGridBlock(blocks.StructBlock):
    """The four-up "Our Principles" grid on the home page."""

    heading = blocks.CharBlock(required=False)
    cards = blocks.ListBlock(CardBlock())
    link_url = blocks.CharBlock(required=False, help_text="Optional link shown below the grid.")
    link_text = blocks.CharBlock(required=False, default="Learn More")

    class Meta:
        icon = "grip"
        template = "core/blocks/card_grid.html"


class EmbedIframeBlock(blocks.StructBlock):
    """Raw iframe embed for Canva decks, the presence map, and similar."""

    title = blocks.CharBlock(help_text="Accessible title for the iframe.")
    src = blocks.URLBlock()
    aspect_ratio = blocks.ChoiceBlock(
        choices=[("56.25", "16:9"), ("75", "4:3"), ("100", "1:1")],
        default="56.25",
    )

    class Meta:
        icon = "media"
        template = "core/blocks/embed_iframe.html"


class AmbassadorApplyBlock(blocks.StructBlock):
    """A call-to-action linking to the native student-ambassador application form.

    Replaces the old Google Form: drop this block into a page body and it renders
    a button pointing at the on-site application (the ambassadors app). The link
    target is fixed, so editors can't point it at the wrong place.
    """

    heading = blocks.CharBlock(required=False, default="Apply")
    text = blocks.RichTextBlock(
        required=False,
        help_text="Optional copy shown above the button.",
    )
    button_text = blocks.CharBlock(default="Apply Now")

    class Meta:
        icon = "form"
        label = "Ambassador application"
        template = "core/blocks/ambassador_apply.html"


class SpeakerBlock(blocks.StructBlock):
    """One speaker in a speaker line-up.

    `photo_url` mirrors the fallback on the `Leader` and `Sponsor` snippets: the
    summit pages carried over from the static site reference photos under
    /static/, and re-uploading every one of them into the image library isn't a
    prerequisite for using this block. An uploaded `photo` wins when both exist.
    """

    name = blocks.CharBlock()
    url = blocks.URLBlock(required=False, help_text="Their site, LinkedIn, or Mastodon.")
    talk_title = blocks.CharBlock(required=False, help_text="The title of their talk, if they have one.")
    photo = ImageBlock(required=False)
    photo_url = blocks.CharBlock(
        required=False,
        help_text="External or /static/ photo URL, used when no image is uploaded.",
    )
    bio = blocks.RichTextBlock(required=False)

    class Meta:
        icon = "user"


class SpeakersBlock(blocks.StructBlock):
    """A grid of speakers under one heading — keynotes, community talks, panels."""

    heading = blocks.CharBlock(required=False, default="Speakers")
    intro = blocks.RichTextBlock(required=False, help_text="Optional copy shown above the grid.")
    speakers = blocks.ListBlock(SpeakerBlock())

    class Meta:
        icon = "group"
        label = "Speakers"
        template = "core/blocks/speakers.html"


class ScheduleItemBlock(blocks.StructBlock):
    time = blocks.CharBlock(help_text='e.g. "09:00" or "8:00am - 9:00am"')
    title = blocks.CharBlock()
    presenter = blocks.CharBlock(required=False)

    class Meta:
        icon = "time"


class ScheduleBlock(blocks.StructBlock):
    """A running order. Use one block per track when a day splits in two."""

    heading = blocks.CharBlock(required=False, default="Schedule")
    intro = blocks.RichTextBlock(required=False, help_text="Optional copy shown above the times.")
    items = blocks.ListBlock(ScheduleItemBlock())

    class Meta:
        icon = "list-ul"
        label = "Schedule"
        template = "core/blocks/schedule.html"

    def get_context(self, value, parent_context=None):
        """Flag whether any row names a presenter.

        A schedule of breaks and logistics has none, and an empty third column
        of em dashes is worse than no column at all — so the template drops it.
        """
        context = super().get_context(value, parent_context=parent_context)
        context["has_presenters"] = any(item.get("presenter") for item in value["items"])
        return context


class BodyStreamBlock(blocks.StreamBlock):
    heading = blocks.CharBlock(form_classname="title", template="core/blocks/heading.html")
    paragraph = blocks.RichTextBlock()
    image = ImageBlock(required=False)
    quote = blocks.BlockQuoteBlock()
    embed = EmbedBlock()
    iframe = EmbedIframeBlock()
    callout = CalloutBlock()
    card_grid = CardGridBlock()
    speakers = SpeakersBlock()
    schedule = ScheduleBlock()
    ambassador_apply = AmbassadorApplyBlock()
    html = blocks.RawHTMLBlock(
        help_text="Raw HTML — available to editors with the required permission only.",
    )
