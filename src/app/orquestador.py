from infra_futuros import get_futures_client
from stories.story_wma_fija import run_story_wma_fija
from stories.story_trading_manual import main as run_story_trading_manual


def main():
    print("=== Orquestador de historias ===")
    client = get_futures_client()

    while True:
        print("\nMenú:")
        print("1) Historia WMA fija")
        print("2) Trading Manual")
        print("3) (placeholder) otras historias")
        print("4) Salir")
        opcion = input("Elige una opción (1/2/3/4): ").strip()

        if opcion == "1":
            run_story_wma_fija(client)
        elif opcion == "2":
            run_story_trading_manual(client)
        elif opcion == "3":
            print("Placeholder: más historias próximamente.")
        elif opcion == "4":
            print("Saliendo del orquestador.")
            break
        else:
            print("Opción no válida.")


if __name__ == "__main__":
    main()
