# Knowledge graph

*[Tiếng Việt](../03-do-thi-tri-thuc.md) · **English***

The knowledge graph turns the notes in a brain into a visual network. Every glowing dot is a Markdown file; every thread is a `[[...]]` wikilink between two notes.

The graph uses a 2D canvas, no WebGL, and loads no library from the internet. It shows notes that have no links yet, supports a timelapse, and can be switched off entirely in Settings.

To see where this data comes from, read [Second Brain: memory, Wiki, INGEST](13-second-brain.md).

## What the graph shows

- **Each node is a note** in the selected brain. Nodes with more connections are larger.
- **Each thread is a `[[...]]` wikilink** between two notes.
- **Node colour is the direct parent folder** of the file.
- **Category labels** around the graph name the largest folders, their note counts and their share of the vault.
- **The AGENTS · SKILLS · WORKFLOWS strip** at the bottom shows how many capabilities exist. Click one to open its management page.

## Opening the graph

1. Open the dashboard, by default at `http://<machine-address>:7777`.
2. In the left navigation rail, open the **Assistant** group and select **Javis**.
3. The graph occupies the middle of the screen.

When you move to another page or open the note editor, the graph pauses itself. Returning to the **Javis** page or closing the editor resumes it.

On screens narrower than 860px, Javis prefers the light interface and opens the **Chat** page directly.

## Turning the graph on or off

1. Open **System → Settings**.
2. Open the **Interface & Brain** group.
3. Find the **Brain graph** card.
4. Click **Disable graph** or **Enable graph**.

While disabled, Javis does not build the graph and opens the **Chat** page directly. The choice is stored in the server settings.

## Choosing a brain

The brain picker sits in the top bar next to the JAVIS OS wordmark. Switching brains updates the graph, the memory, the agent/skill/workflow counts, the file tree and the conversation panel together.

Three small buttons sit next to the picker:

| Button | What it does |
|---|---|
| ➕ | Create a new brain in the `brains` folder. |
| 🗑 | Delete the selected brain after you confirm its name. **Brain Default** cannot be deleted. |
| 📁 | Pick any notes folder on the machine as a source. |

External folders are remembered in the list so you can pick them again. Clicking 🗑 on an external source only removes it from the menu; it does not delete anything on disk.

## Moving around and reading the graph

- **Drag the background** to move the network.
- **Scroll the wheel** to zoom in or out.
- **Drag a node** to move it temporarily; on release it settles back into balance.
- **Hover a node** to show the note name, highlight that node and its neighbours, and dim the rest.
- **Click a node** to open the note in the editor.
- **Click a category label** to spotlight that folder's cluster. Click the label again or click the background to clear the filter.

Once the physics settle, Javis fits the whole network to the frame automatically.

## Opening and editing a note from a node

1. Click a node.
2. The note editor opens over the graph area.
3. Read, edit or download the file as usual.
4. Click ✕ or press Esc to close and restart the graph.

For `.md` files the editor has two modes, **Edit** and **Source**. The toolbar has:

| Button | What it does |
|---|---|
| 💾 Save | Write the content to the file; `Ctrl+S` works too. |
| ✎ | Rename the file. |
| 🗑 | Delete the note after confirmation. |
| ↗ | Open the raw file in a new tab. |
| ⤓ Download | Download the file. |
| ⛶ | Enlarge or shrink the editor. |
| ✕ | Close the editor. |

Clicking a node only opens the file; it does not send a question into the chat. To have Javis summarise or analyse it, ask in the conversation panel.

## Hiding the overlay

The eye button in the top right of the graph area hides or shows:

- category labels;
- the AGENTS · SKILLS · WORKFLOWS strip.

The state is remembered in the browser and synced across tabs.

## The "brain lifetime" timelapse

The clock button under the eye replays how the brain grew:

1. The graph starts empty.
2. Notes appear in file creation order, roughly 0.16 seconds apart.
3. A thread only appears once both of its ends exist.
4. Click the button again to stop; the full graph is restored.

## Node colours by folder

Javis uses a high-contrast palette and assigns colours to direct parent folders in turn. Numeric prefixes such as `07 - ` are ignored when comparing names, so `07 - Wiki` and `Wiki` count as the same category.

The node colour is also used for the "% of Vault" part of the category label. Switching between light and dark themes swaps to a matching palette while keeping each folder's colour group.

## The statistics line

The top bar carries a line like:

```text
42 notes · 87 connections
```

- **notes**: how many notes are displayed, including notes with no wikilinks yet.
- **connections**: the total number of valid wikilinks between notes.

Other states are **Loading...**, **Error: ...**, or a warning that the graph library could not load.

## Real-time updates

The graph watches the brain and updates itself when a note or a link appears:

1. A new node pops in and shrinks to its normal size.
2. The statistics line updates with a soft flash.

If the watch connection drops, Javis reconnects. A periodic scan also catches anything the watch missed.

## Reacting to voice and status

- While you speak or Javis reads an answer, nodes swell slightly with the volume.
- When Javis switches to **THINKING**, the network changes rhythm.
- At rest, nodes breathe gently with offset phases.

## How the graph is built

1. Javis scans up to 2,000 `.md` files in the selected source.
2. Each file becomes a node; the node name is the filename without its extension.
3. Javis finds `[[...]]` wikilinks; each link to another file becomes an edge.
4. The `[[folder/Name|alias]]` form is supported; Javis takes the filename part to connect.
5. Javis counts notes per parent folder and picks up to the 8 largest folders as labels.

## Common problems

- **The graph is empty or has few nodes**: check which brain is selected and whether the source contains `.md` files.
- **The graph library will not load**: reload the page. The library is served from the Javis server itself, so the error usually means a partial page load or static files not being served.
- **The statistics line reads "Error"**: an external source may have moved or lost read permission.
- **The graph is frozen**: check whether you are on another page, have the editor open, are on a narrow screen, or have disabled the graph in Settings.
- **Opening Javis jumps straight to Chat**: the screen is narrow or the graph is disabled.
- **A new node has not appeared**: wait for the watch connection to reconnect, or switch brains and back to reload.

## Related

- [Chat & voice](02-chat-and-voice.md)
- [Second Brain: memory, Wiki, INGEST](13-second-brain.md)
- [File manager](05-file-manager.md)
- [Agents & Workflows](07-agents-and-workflows.md)
- [Skills](06-skills.md)
- [Backing the brain up to GitHub](18-github-backup.md)
- [Troubleshooting & FAQ](17-troubleshooting.md)
