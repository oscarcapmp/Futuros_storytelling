from infra_futuros import get_futures_client
from stories.story_wma_fija import run_story_wma_fija
from stories.story_trading_cola import run_story_trading_cola


def main():
    print("=== Orquestador de historias ===")
    client = get_futures_client()

    while True:
        print("\nMenú:")
        print("1) Historia WMA fija")
        print("2) (placeholder) otras historias")
        print("3) Salir")
        opcion = input("Elige una opción (1/2/3): ").strip()

        if opcion == "1":
            print("\nModo de entrada:")
            print("a) GO a MARKET (actual)")
            print("b) GO COLA (cola techo/piso)")
            sub = input("Elige modo (a/b) [a]: ").strip().lower() or "a"
            if sub == "b":
                run_story_trading_cola(client)
            else:
                run_story_wma_fija(client)
        elif opcion == "2":
            print("Placeholder: más historias próximamente.")
        elif opcion == "3":
            print("Saliendo del orquestador.")
            break
        else:
            print("Opción no válida.")


if __name__ == "__main__":
    main()
