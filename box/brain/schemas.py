"""What the Box Brain asks Gemini for. Kept small: fewer output tokens = faster answers."""

from typing import Literal

from pydantic import BaseModel, Field


class Param(BaseModel):
    # Pairs rather than a dict: Gemini's response schema has no free-form maps.
    name: str
    value: str


class Plan(BaseModel):
    heard: str = Field(default="", description="What the user asked, in their own words and language (written out "
                       "from the recording when the request was spoken). Empty if the recording holds no request.")
    summary: str = Field(description="ONE short question in the user's language naming the concrete result, e.g. 'Shall I set an alarm for 7 AM?'. Read aloud, under 20 words.")
    steps: list[str] = Field(description="2-4 very short concrete actions, user's language, shown on screen.")
    refused: bool = Field(description="True for anything harmful, moving money to people, or sharing OTPs/PINs/passwords.")
    app: str = Field(description="Main app to use, e.g. 'YouTube', 'Clock', 'Chrome'. Empty if none.")
    playbook: Literal["none", "set_alarm", "set_timer", "call", "send_message", "play_video", "directions", "volume",
                      "battery", "explain_screen", "missed", "scam_check", "read_medicine", "read_list", "open_link",
                      "web_search", "open_app"] = Field(
        description="A shortcut that does the task (or its first part) without step-by-step AI: "
        "set_alarm (params hour 0-23, minute, label), set_timer (params seconds, label), "
        "call (param contact + contact_latin, or number), send_message (params contact + contact_latin or number, "
        "text, app whatsapp|sms), play_video (param query), directions (params place, mode driving|walking|transit), "
        "volume (param level up|down|max), battery (no params), explain_screen (no params), missed (no params), "
        "scam_check (no params), read_medicine (param send_to: a contact, if they want it sent), read_list (no params), "
        "open_link (param url), "
        "web_search (param query), open_app (param app).")
    params: list[Param] = Field(description="Playbook parameters, e.g. [{name: 'hour', value: '7'}]; for a task done "
                                "step by step, its details (e.g. [{name: 'item', value: 'milk'}]).")
    routine: str = Field(default="", description="For a task done step by step in an app: a short snake_case name for "
                         "this kind of task, the same every time it is asked (e.g. 'blinkit_add_item'); else ''.")
    goal: str = Field(description="Precise English instruction for the phone operator, all the way to the result.")
    done_message: str = Field(description="What to say when it worked, user's language, e.g. 'Your alarm is set for 7 AM.'")


class Explanation(BaseModel):
    """'What is this screen?' in plain words, with the safest next step."""
    explanation: str = Field(description="2-3 short, calm sentences in the user's language: what this screen is "
                             "(which app, what it is for) and what is safe to do next.")
    risk: Literal["none", "caution", "danger"]
    suggest: Literal["none", "back", "home"] = Field(description="The safest step when there is risk, else none.")


class Missed(BaseModel):
    summary: str = Field(description="What the user missed, in their language, 2-5 short sentences to be read aloud.")


class ScamVerdict(BaseModel):
    risk: Literal["none", "low", "medium", "high"]
    reasons: list[str] = Field(description="Short English reason codes, e.g. 'fake_kyc', 'asks_otp'.")
    impersonates: str = Field(description="Organisation the message pretends to be (e.g. 'SBI', 'India Post'), or ''.")
    warning: str = Field(description="1-2 calm sentences in the user's language. When risk is medium or high: do not "
                         "open the link and do not share any details or OTP. Never repeat the link. '' if none/low.")


class MedicineInfo(BaseModel):
    """What a medicine label says, read from a photo. Identification only, never medical advice."""
    readable: bool = Field(description="False if the label can't be read reliably.")
    name: str = Field(description="Brand name as printed, e.g. 'Dolo 650', or ''.")
    generic: str = Field(description="Active ingredient(s) and strength, e.g. 'Paracetamol 650 mg', or ''.")
    expiry: str = Field(description="Expiry as printed, e.g. '08/2027', or ''.")
    expired: bool = Field(description="True only if the printed expiry is clearly before today's date.")
    say_to_user: str = Field(description="1-2 short sentences in the user's language: what medicine this looks like "
                             "(and if it has expired); if unreadable, how to hold it better.")
    caption: str = Field(description="For sending to family or a doctor, in the user's language, first person, under "
                         "40 words, e.g. 'This is the medicine I have: Dolo 650 (Paracetamol 650 mg). Is it right?'")


class GroceryItem(BaseModel):
    name: str = Field(description="As a shop would call it, in English, e.g. 'tomatoes', 'toor dal'.")
    quantity: str = Field(description="As written, e.g. '1 kg', '2 packets', or ''.")


class GroceryList(BaseModel):
    readable: bool
    items: list[GroceryItem]
    say_to_user: str = Field(description="In the user's language: the items read back simply. If unreadable, how to "
                             "hold the list better.")


class Reply(BaseModel):
    """A spoken answer to one of the box's yes/no questions."""
    answer: Literal["yes", "no", "unclear"]


class Action(BaseModel):
    kind: Literal["tap", "long_press", "type", "scroll", "back", "home", "open_app", "open_link", "wait", "hand_over"]
    element: int = Field(description="Index [n] of the target element in the list, or -1 if none / using x,y.")
    label: str = Field(description="Visible text of the target element (used to find it again if the screen moved), or ''.")
    x: int = Field(description="0-999 horizontal position if no element fits, else -1.")
    y: int = Field(description="0-999 vertical position if no element fits, else -1.")
    text: str = Field(description="Text to type (kind=type), app name (open_app) or URL (open_link); else ''.")
    press_enter: bool = Field(description="Press Enter after typing.")
    direction: Literal["up", "down", "none"] = Field(description="Scroll direction for kind=scroll; else 'none'.")
    intent: str = Field(description="What this does, a few words in the user's language, e.g. 'Tapping Add alarm'.")
    announce: bool = Field(description="Say it aloud: only key moments (item added, alarm set, fare found).")
    expect: str = Field(description="Text that should be visible right after this action (lets the box check without asking AI), or ''.")
    irreversible: bool = Field(description="True for Place order, Pay, Send, Book/Request ride, Delete, Install, Confirm.")


class Turn(BaseModel):
    need_screenshot: bool = Field(description="True only if the element list is not enough to decide (icons without text, "
                                  "images, maps); then return no actions and the box sends a screenshot.")
    actions: list[Action] = Field(description="1-5 actions to run in order. Stop the list at any irreversible action.")
    done: bool = Field(description="True only when the CURRENT screen shows the goal achieved, or it cannot be done.")
    success: bool
    message: str = Field(description="When done: 1 short sentence for the user in their language; else ''.")
