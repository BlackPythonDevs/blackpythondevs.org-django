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


class CTABlock(blocks.StructBlock):
    """A single call-to-action button, styled per the design system.

    Target a Wagtail page with the page chooser, or an external site with
    the URL field; the page wins when both are set. Leave the button text
    blank to render nothing.
    """

    button_text = blocks.CharBlock(
        required=False,
        help_text="Label shown on the button. Leave blank to render nothing.",
    )
    style = blocks.ChoiceBlock(
        choices=[
            ("primary", "Primary"),
            ("secondary", "Secondary"),
        ],
        default="primary",
        help_text="Primary is cyan, secondary is gold — see the design system's button variants.",
    )
    page = blocks.PageChooserBlock(
        required=False,
        help_text="Internal target — takes precedence over the external URL.",
    )
    url = blocks.URLBlock(
        required=False, label="External URL", help_text="External target, e.g. https://example.com/join."
    )

    class Meta:
        icon = "link"
        label = "CTA"
        template = "core/blocks/cta.html"


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


class DonateBlock(blocks.StructBlock):
    """Embedded CommitChange donation form.

    `designation` goes to CommitChange's `data-designation`, so every gift made
    through this form is recorded under that fund and funds raised can be
    aligned with it.
    """

    heading = blocks.CharBlock(required=False)
    text = blocks.RichTextBlock(required=False)
    designation = blocks.CharBlock(
        required=False,
        max_length=100,
        help_text="Fund the gifts are designated to (e.g. 'Leadership Summit').",
    )
    amounts = blocks.CharBlock(
        required=False,
        default="15,25,50,100,250,500",
        help_text="Comma-separated suggested amounts in dollars.",
    )
    disable_monthly = blocks.BooleanBlock(
        required=False,
        label="Disable monthly giving",
        help_text="Make every gift through this form one-time. Leave unchecked to let donors choose.",
    )

    class Meta:
        icon = "pick"
        label = "Donate form"
        template = "core/blocks/donate.html"


class BodyStreamBlock(blocks.StreamBlock):
    heading = blocks.CharBlock(form_classname="title", template="core/blocks/heading.html")
    paragraph = blocks.RichTextBlock()
    image = ImageBlock(required=False)
    quote = blocks.BlockQuoteBlock()
    embed = EmbedBlock()
    iframe = EmbedIframeBlock()
    callout = CalloutBlock()
    card_grid = CardGridBlock()
    cta = CTABlock()
    ambassador_apply = AmbassadorApplyBlock()
    donate = DonateBlock()
    html = blocks.RawHTMLBlock(
        help_text="Raw HTML — available to editors with the required permission only.",
    )
