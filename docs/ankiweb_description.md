<p>AnkiGit provides Git-based version control for your Anki collections. Export your collection to a human-readable Git repo, track every change, collaborate on decks, and roll back to any point in history.</p>

<h2>How It Works</h2>
<p>AnkiGit exports every note as a standalone Markdown file inside a local Git repository. Snapshots happen on demand or automatically on close — each commit records the full state of your collection in human-readable form.</p>


<img src="https://raw.githubusercontent.com/Alexander-Nilsson/Anki-git/main/docs/diffUI.png" width="500">
<img src="https://raw.githubusercontent.com/Alexander-Nilsson/Anki-git/main/docs/configUI.png" width="500">


<h2>Features</h2>
<ul>
  <li><strong>Export</strong> — snapshot your collection to a Git repo (one Markdown file per note)</li>
  <li><strong>Incremental export</strong> — only re-export changed notes since the last snapshot</li>
  <li><strong>Import</strong> — apply changes from your Git repo back into Anki</li>
  <li><strong>Selective import</strong> — pick individual notes and notetypes via checkboxes</li>
  <li><strong>Diff preview</strong> — git-style diff viewer before export/import</li>
  <li><strong>Conflict resolution</strong> — three-way merge detection with a Qt dialog and auto-resolve modes</li>
  <li><strong>Notetype tracking</strong> — clean YAML export with CSS separated into its own file</li>
  <li><strong>Auto-import on startup</strong> — automatically check for repo changes when Anki opens</li>
  <li><strong>Auto-snapshot on close</strong> — snapshot changes when Anki closes</li>
  <li><strong>Remote push</strong> — auto-push to GitHub/GitLab after snapshot</li>
</ul>

<h2>Example Note Format</h2>
<p>Each note becomes <code>decks/&lt;DeckName&gt;/&lt;nid&gt;.md</code>:</p>
<pre><code># Note
guid: dc6H$t-~MK
notetype: iKnow! Sentences
### Tags
languages
japanese
jp-sentences
jp-transportation
## Expression
駅からはタクシーに&lt;b&gt;乗って&lt;/b&gt;ください。
## Meaning
Please take a taxi from the station.
乗る -- ride, take
## Reading
えき からは たくしー に &lt;b&gt;のって&lt;/b&gt; ください
## Audio
[sound:e3c984736d8b1c2bdc467f2a1c98659a.mp3]
## Image_URI
&lt;img src="e2d8a60b59f2be8ebcbffafa165c7a0d.jpg"&gt;
## iKnowID
sentence:247153
## iKnowType
sentence
</code></pre>

<h2>Quick Install</h2>
<p><strong>Anki Code:</strong> <code>1384407975</code></p>
<hr>
<p><a href="https://github.com/Alexander-Nilsson/Anki-git">Source Code</a> | AGPL-3.0-only</p>
