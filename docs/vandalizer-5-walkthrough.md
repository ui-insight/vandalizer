# Vandalizer 5.0 launch walkthrough

The landing page includes a silent, 16:9 launch walkthrough at `frontend/public/videos/vandalizer-5-walkthrough.mp4`. It is intentionally grounded in the V5 release narrative and uses clearly illustrative R01 material—no customer data or live project is shown.

## On-screen sequence

| Chapter | On-screen line |
| --- | --- |
| Vandalizer 5.0 | Everything your office can do. Now, you just ask. |
| Project-scoped agent | Give the agent a bounded job, then watch every step surface in chat. |
| Natural-language tools | Find, know, extract, run, and verify—without leaving the conversation. |
| Projects | Every file, trusted tool, and teammate stays in the context of the work. |
| Trust layer | Citations, quality signals, and test cases make the answer reviewable. |
| Human control | The agent prepares the work. Your team stays at the approval gate. |
| Close | Built for the work that needs to be right. |

## Re-capture

Start the frontend, then run the capture command from `frontend`. Use `WALKTHROUGH_ORIGIN` when the app is running anywhere other than port 5173.

```bash
WALKTHROUGH_ORIGIN=http://127.0.0.1:5175 npm run capture:launch-walkthrough
```

The capture script creates the MP4 and poster image, then the landing page serves them by default. Set `VITE_DEMO_VIDEO_URL` to override the bundled asset with a hosted video or an approved live-product recording.
