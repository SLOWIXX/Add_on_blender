# Softmove : Blender Accessibility Addon 4.2 LTS to 3.6 LTS

<img width="2235" height="1316" alt="logo-soft-move" src="https://github.com/user-attachments/assets/10e2f59b-c386-4d72-a8fd-1a871fd463d7" />

**Softmove** est un addon pour **Blender** conçu pour aider les artistes souffrant de **handicaps moteurs** (tremblements, Parkinson, dyspraxie) à modéliser en 3D avec précision.
Celui ci a pour but de modifier le curseur dans la vue 3d, pour le remplacer par un curseur anti-tremblement avec une aim assist et un systeme de preseletion.

https://github.com/user-attachments/assets/6fe61c5c-86ea-44c4-9212-694cf5f8028a

## Le Problème
Dans Blender, la sélection d'un Vertex demande une precision surtout dans les zones dense.

Pour une personne ayant des tremblement :
1.  Le curseur vibre constamment, rendant le clic impossible.
2.  Les outils de lissage existants ("Lazy Mouse") ne fonctionnent que pour le *Sculpting*, pas pour l'interface ou la modélisation.
3.  L'utilisateur clique souvent à côté ou sélectionne le mauvais objet.

## La Solution 
Séparer l'intention du mouvement de l'utilisateur, des mouvement non voulu grace a une separation du curseur en 3 partie :
1. **Une zone de tolérance :** tant que le tremblement reste dans cette zone le curseur bouge pas. (permet de filtrer les petits tremblements).
2. **Une Zone de sélecion :** Zone permettant de sélectionnés.
3. **Curseur originel:** Vrai position de la souris (a un effet de laisse/élasticité avec la zone de tolérence).

 <img width="311" height="312" alt="Capture d&#39;écran 2026-02-12 235938" src="https://github.com/user-attachments/assets/49d94f85-a41a-4650-9abf-e0d42a424099" />
 
## Les fonctionalité Clés

* ** Moyenne glissante :** permet de filtrer les mouvement dans un nombre de frame. (filtre meme les plus gros tremblement)
* ** Aim assist :** Le curseur ralenti quand on passe sur un objet 3D et sélection le vertice le plus prés. (le curseur comprend la 3D)
* ** Pré-sélection :** le curseur met en surbriance les Vertices/Edge et Face en surbriance
  image de préselection a mettre plus tard
* ** 100% customisable :** Rayons, vitesse, aim-assist , couleur etc.. (Via le paneau N)

## Instalation 
1.  Télecharger et extraire "softmove.py"
2.  Ouvrez le dossier de config blender puis [version]>scripts>startup
3.  Coller le fichier dans le dossier "startup"
4.  Démarrer blender et appuyer sur F5 pour Activer/Désactivé le curseur

## Réglages (N-Panel)
* **Zone de tolérance :** Agrandissez-la si vous tremblez beaucoup.
* **Friction :** Augmentez-la pour que le curseur ralentisse  plus sur les objets 3D.
* **Lissage :** Nombre de frames pour calculer la moyenne (plus haut = plus fluide mais plus de latence).

<img width="239" height="598" alt="menu" src="https://github.com/user-attachments/assets/a3157c00-03de-4fbb-874b-b6bb59e88b63" />

##Architecture et librairie 
* ** gpu :** Pour déssiné le curseur ainsi que la préselection dans le viewport 3D.
* ** bmesh :** Pour avoir la topologie de l'objet sur le quel on est, et savoir ou sont les vertex et a quoi ils sont lié.
* ** View3d_utils : ** Pour projeter de la 3d à la 2d et inversement de façon ultra simple.

## Future 
** Ajout systeme pour lock un racourci.
** Adapté toutles outil de blender au curseur.
** Mettre la souris avec un systeme de morphing dans les menu.
** Systeme pour changé la taille des menus et du texte.

> **Note de conception :**

Premièrement, on a identifié un problème : Blender demande beaucoup de précision dans son utilisation, même pour des utilisateurs non handicapés, ça peut arriver de sélectionner les mauvais vertices. 
On s'est donc dit que ça devait être encore plus dur pour des personnes qui sont atteintes de tremblements d'être précises dans le viewport de Blender. De là nous est venue l'idée d'un curseur anti-tremblement.

Maintenant, il nous fallait une solution technique pour faire ce curseur. On a pensé d'abord à une souris en cercle avec un point dedans. 
Le cercle devait se déplacer seulement quand le point (curseur d'origine) est à l'extrémité de celui-ci, donc le grand cercle faisait office d'outil de sélection et de zone morte pour la souris. 
De là nous est venu un autre problème : une personne atteinte de forts tremblements aurait une très grande zone morte et donc, par dépit, une très grosse zone de sélection.

Donc, pour répondre à ce problème, on a décidé de rajouter deux features : 
La première a été de rajouter un troisième cercle pour séparer la zone de sélection et la zone morte pour qu'une personne à forts tremblements puisse garder la précision d'une petite zone de sélection avec une plus grande zone morte. 
La deuxième, ajouter un système de preview de sélection puisque le curseur pouvait parfois être assez gros et englober deux vertices ou edges s'ils sont trop proches l'un de l'autre. 
Puis, de là, on avait déjà un truc qui marchait un peu mais qui était loin d'être parfait ; on a donc cherché à l'améliorer et on s'est donc souvenu de ce que Peter avait dit par rapport aux jeux vidéo, qu'il y avait de gros efforts faits dans cette industrie autour de l'accessibilité. 
De là nous est venue l'idée d'une aim assist, étant familiers avec les jeux vidéo, on savait comment ça fonctionnait et quel était le principe. On a donc ajouté un système de ralentissement quand on passe au-dessus d'un objet 3D, on a rajouté un système de sensibilité et on a rajouté un système de magnétisme : on prend le vertex le plus proche.

De là, on a commencé à avoir un truc un peu mieux, mais la suppression de tremblement n'était pas parfaite car on a constaté que si la personne tremblait dans le même sens que son intention de mouvement, comme elle était par défaut déjà sur le bord de la zone morte, le tremblement n'était pas supprimé. 
On a donc fait des recherches sur comment fonctionnaient des systèmes un peu similaires et on est tombé sur deux gros concepts.
Le premier, qui règle notre souci, est la moyenne glissante : on calcule le mouvement moyen sur un nombre de frames réglable. 
Par exemple, si sur 12 frames la personne a un tremblement qui la fait passer d'une coordonnée x=100 à une coordonnée x=200 mais que la personne revient à une coordonnée x=150, bah le déplacement va se faire en x=150.
Ainsi on corrige le tremblement même dans la direction d'intention de la personne.

L'autre solution est l'ajout d'une inertie au point curseur : celui-ci va tendre à aller vers notre souris (invisible) au lieu d'aller directement à la souris (invisible). 
Le point est utile dans ce contexte car il permet de lisser la trajectoire en filtrant les micro-mouvements brusques.

