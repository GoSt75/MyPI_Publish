---
name: mypi-publish-menus
description: Publication automatique des menus NOURA sur MyPI
---

## Objectif
Publier automatiquement les menus des établissements NOURA sur la plateforme MyPI via le navigateur Chrome.

## Étapes à suivre

1. **Vérifier que le fichier de configuration existe** à l'emplacement suivant sur le disque de l'utilisateur :
   `C:\Users\gost9\Documents\Claude\mypi_config.json`
   - Si le fichier n'existe pas ou contient encore les valeurs par défaut (`votre_email@exemple.com`), arrête la tâche et notifie l'utilisateur qu'il doit renseigner ses identifiants dans ce fichier avant la prochaine exécution.

2. **Publier les menus via le navigateur Chrome** (utiliser les outils Claude in Chrome) :
   a. Naviguer vers `https://configurateur.mypi.net/menus`
   b. Ouvrir le sélecteur d'établissement en cliquant sur le dropdown en haut à gauche
   c. Pour chaque établissement listé dans `mypi_config.json` (champ `etablissements`) :
      - Sélectionner l'établissement via son radio button (utiliser l'outil `find` avec le nom exact)
      - Attendre 3 secondes le chargement de la page
      - Ouvrir le panneau "Gestion de la carte web" en cliquant sur l'icône fusée (rocket) en haut à droite
      - Attendre 2 secondes que le panneau s'ouvre
      - Cliquer sur le bouton **Publier** bleu
      - Attendre 6 secondes que la publication se termine
      - Noter le statut de chaque plateforme visible (PiClick, Uber Eats, Deliveroo)
      - Fermer le panneau (croix ×)
      - Ouvrir à nouveau le sélecteur pour passer à l'établissement suivant

3. **Rapporter le résultat** dans la session :
   - Succès : confirmer que les publications ont été effectuées avec le statut de chaque plateforme
   - Échec : décrire l'erreur rencontrée

## Contraintes
- Les identifiants MyPI sont dans `mypi_config.json` — ne jamais les afficher dans les logs.
- Si l'interface MyPI a changé (éléments introuvables), le signaler dans le rapport de session.
- Le sélecteur d'établissement utilise des Web Components (shadow DOM) — préférer l'outil `find` avec le nom exact de l'établissement pour localiser le radio button.

## Succès attendu
Publications effectuées pour tous les établissements listés dans `mypi_config.json`, statut des plateformes rapporté dans la session.