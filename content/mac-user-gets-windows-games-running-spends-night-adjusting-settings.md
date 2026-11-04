---
title: Mac User Finally Gets Windows Games Running, Spends the Whole Night Adjusting Settings Instead and Calls It His Best Gaming Session Ever
slug: mac-user-gets-windows-games-running-spends-night-adjusting-settings
dek: A free, unofficial project called FX Steam Launcher runs SteamOS on Apple Silicon Macs, with Windows games working through a stack of translation layers.
section: Tech
date: 2026-11-03T09:11:00-05:00
author: Dex Voltage
author_title: Technology Editor
dateline: CUPERTINO-ADJACENT
x_post: https://x.com/ChaoticNewsHQ/status/2117620773733163240
x_post_text: TECH DESK: Mac User Finally Gets Windows Games Running, Spends the Whole Night Adjusting Settings Instead and Calls It His Best Gaming Session Ever 🍎
x_post_date: November 3, 2026
x_replied_to: pcgamer
x_replied_to_url: https://x.com/pcgamer/status/2117617217642856754
source_url: https://www.pcgamer.com/software/operating-systems/modders-bring-steam-frame-build-of-steamos-and-all-of-its-translation-layer-goodness-to-mac/
source_title: Modders bring Steam Frame build of SteamOS and all of its translation layer goodness to Mac
source_outlet: PC Gamer
---
[PC Gamer](https://x.com/pcgamer) posted on X that an open-source project now brings SteamOS, plus playable Windows games, to the Mac. Mac gamers everywhere screamed, then opened a settings menu, and have not been seen since.

## What Actually Happened

The project is called **FX Steam Launcher**, and it lives on GitHub. It runs the ARM64 version of SteamOS, the one built for Valve's Steam Frame, on Apple Silicon Macs. Windows games work thanks to Proton 11 and FEX.

It is not a real install. SteamOS runs inside a virtual machine on your Mac. The launcher downloads the official SteamOS image straight from Valve and even handles updates. It is unofficial, so expect some rough edges.

Here is the fun part: the translation chain. Your game's graphics go through DXVK (for DirectX 9, 10 and 11) or VKD3D-Proton (for DirectX 12), then through MoltenVK or KosmicKrisp, and finally to Apple's Metal. That is more handoffs than a group project. The launcher needs macOS 15 or newer, but KosmicKrisp needs macOS 26 or later.

Does it work? YouTuber ETA Prime tried it on an M4 Max and got over 70 frames per second at high settings in The Witcher 3, Stellar Blade and Left 4 Dead 2, with Left 4 Dead 2 going past 200. PC Gamer notes Stellar Blade ran at just 800p, the others at 1080p at most, and not every game ran that well.

## Our Take (This Part Is Made Up)

We spoke to a Mac user who finally got a Windows game running at 11pm. He then spent the rest of the night switching between windowed and fullscreen, adjusting the resolution, and testing which layer was doing what. He never pressed Start. He called it "the best gaming session of my life," and honestly, we believe him.
