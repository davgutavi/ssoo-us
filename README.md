# ssoo-us

### Máquinas virtuales con cloud-init en los servidores de la asignatura
**Asignatura: Sistemas Operativos — Universidad de Sevilla**

> **En desarrollo.** Este curso siga usando `ci-provision.sh` y `ci-diagnosis`.
> `ssoo-us provision` y `ssoo-us diagnosis` ya hacen lo mismo que ellas y están
> instalados en los servidores, pero se estrenan el curso que viene.

`ssoo-us` reúne en un solo programa las dos herramientas de la asignatura. Está
instalado en los servidores de la asignatura para todos los usuarios: no hay que
descargar nada.

- `ssoo-us provision`: crea máquinas virtuales con cloud-init en su silo, como
  `ci-provision.sh`, con las mismas opciones.
- `ssoo-us diagnosis`: revisa la construcción de una máquina y dice qué falla,
  como `ci-diagnosis`, con las mismas opciones.

```
ssoo-us --version
ssoo-us -h
ssoo-us provision -h
ssoo-us diagnosis -h
```

Si va a modificar la herramienta, lea [DESARROLLO.md](DESARROLLO.md).
