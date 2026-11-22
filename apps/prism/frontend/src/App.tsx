import { FormDialogProvider } from "@/components/ui";
import { LegacyDataProvider } from "@/features/legacy/LegacyDataProvider";
import { PrismsProvider } from "@/features/prisms/PrismsProvider";
import { AppProvider } from "@/shell/AppProvider";
import { Shell } from "@/shell/Shell";

export function App() {
  return (
    <AppProvider>
      <FormDialogProvider>
        <PrismsProvider>
          <LegacyDataProvider>
            <Shell />
          </LegacyDataProvider>
        </PrismsProvider>
      </FormDialogProvider>
    </AppProvider>
  );
}
