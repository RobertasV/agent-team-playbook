# Agent team playbook

Kaip mažai AI agentų komandai dirbti vienam žmogui (savininkui) taip, kad būtų tvarka ir netaškytų žetonų:

- viena nuolatinė sesija vienai pareigybei (programuotojas, tikrintojas, taisyklių peržiūrėtojas);
- užduočių eilė – GitHub užduotys (issues); ką praleisti, rodo etiketės; būsenas keičia agentas, savininkas tik rašo;
- agentai GitHub'e rašo atskira AI paskyra, ne savininko vardu;
- savininko klausimas nėra sprendimas; leidimas – tik po patikros ir savininko žodžio.

Skilas agentams parašytas angliškai (taip pigiau žetonų prasme ir tinka bet kuriam agentui).

## Kas viduje

| Kelias | Kas |
|---|---|
| `skill/agent-team/SKILL.md` | Skilas: taisyklės agentams |
| `tools/agentq` | Eilės įrankis: `queue`, `take`, `ask`, `defer`, `wait`, `check`, `setup` |
| `config.example.json` | Nustatymų pavyzdys |
| `tests/` | Testai su netikru `gh` (tikro GitHub neliečia) |

## Diegimas

Reikia: `git`, `gh`, `python3`.

1. **AI paskyra.** Susikurk atskirą GitHub paskyrą agentams (GitHub leidžia vieną nemokamą „mašinos“ paskyrą žmogui), pakviesk ją į savo projektus su teise **Write**. Šiame kompiuteryje prisijunk ja: `gh auth login` (patvirtinimo puslapį atidaryk naršyklės lange, kuriame esi prisijungęs AI paskyra). Savo paskyra lieka prisijungusi, bet neaktyvi (`gh auth switch` perjungia).
2. **Paketas:** `git clone` šį projektą, pvz. į `~/Sites/agent-team-playbook`.
3. **Tik pasirinktiems projektams.** Kiekviename projekte, kuriame agentai turi dirbti pagal šias taisykles:
   - nustatymai: nukopijuok `config.example.json` į savo vietą, įrašyk savo paskyras, repozitoriją ir etiketes, o projekto šaknyje padaryk nuorodą `.agentq.json` į tą failą;
   - Claude Code: `ln -s ~/Sites/agent-team-playbook/skill/agent-team <projektas>/.claude/skills/agent-team`;
   - Codex: projekto `AGENTS.md` įrašyk eilutę „Team rules and the task queue: read `~/Sites/agent-team-playbook/skill/agent-team/SKILL.md`“;
   - kad šie failai nepatektų į projekto git: įrašyk `.agentq.json` ir `.claude/skills/agent-team` į `.git/info/exclude`.
4. **Etiketės:** projekto aplanke `~/Sites/agent-team-playbook/tools/agentq setup` sukuria trūkstamas.
5. **Patikrinimas:** `tools/agentq queue` parodo eilę.

Kituose projektuose skilas ir įrankis neveikia: nėra nei nuorodos į skilą, nei `.agentq.json`.

## Kasdien

- Agentas: `agentq queue` (eilė ir nauji savininko komentarai), tada `take` / `ask` / `defer` / `wait`.
- `agentq check` randa neatitikimus (pamiršta „in progress“, neatsakytas savininko komentaras, užduotis, kurios laukta, jau uždaryta); `check --fix` sutvarko, ką gali. Jį galima leisti kartą per dieną laikmačiu – agento ir žetonų tam nereikia.

## Atnaujinimas

`git pull` paketo aplanke; kas pasikeitė – `CHANGELOG.md`. Nuorodos rodo į paketą, todėl projektai gauna naują versiją iškart.

## Testai

```bash
python3 -m unittest discover -s tests
```

Paketas skirtas dalintis, todėl jame negali būti jūsų privačių vardų. Jų sąrašą laikykite už paketo ribų (`~/.config/agentq/private-words.txt` arba `AGENTQ_PRIVATE_WORDS=<failas>`), ir testas patikrins, kad nė vienas jų nepateko į paketą.
