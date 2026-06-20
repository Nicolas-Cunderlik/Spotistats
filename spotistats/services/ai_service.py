"""AI service wrapper around existing `auth.getOpenAIClient()` with defensive parsing."""
import logging
import auth

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                self._client = auth.getOpenAIClient()
            except Exception:
                logger.exception("Failed to initialize OpenAI client")
                self._client = None

    def get_chord_suggestions(self, track_name, artist):
        self._ensure_client()
        if not self._client:
            return []

        try:
            response = self._client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "developer", "content": "You are a music expert who provides accurate sound design suggestions to imitate to vibe of songs."},
                          {"role": "user", "content": f"Given the song '{track_name}' by {artist}, generate three chord progressions, using the following format, that would imitate the vibe of the song (your output will be parsed at each underscore). Do not provide any additional information/words: Cmaj-Fmaj-Gmaj7-Amaj, Dsus-Gmin-Amaj11-Bmin, Fmaj-Gmaj7-Asus-Bbmaj"}],
                max_tokens=50,
                timeout=15,
            )

            choices = getattr(response, 'choices', None)
            if not choices:
                return []

            content = None
            try:
                content = choices[0].message.content
            except Exception:
                try:
                    content = choices[0]['message']['content']
                except Exception:
                    content = None

            if not content:
                return []

            chord_progressions = content.split(", ")
            while len(chord_progressions) < 3:
                chord_progressions.append("-")
            return chord_progressions[:3]
        except Exception:
            logger.exception("AI request failed")
            return []
